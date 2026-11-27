#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grademe_push_swap.py - Avaliador automatico (NAO oficial) do projeto push_swap da 42.

Uso (dentro da pasta do projeto):
    python3 grademe_push_swap.py [opcoes]

O programa NUNCA modifica os ficheiros originais: copia o projeto para uma
pasta temporaria e compila/testa apenas essa copia.

Corre `python3 grademe_push_swap.py --help` para ver todas as opcoes.
"""

import argparse
import itertools
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections import deque

# --------------------------------------------------------------------------- #
#  Configuracao (ajusta aqui se a tua versao do enunciado for diferente)       #
# --------------------------------------------------------------------------- #

NAME = "push_swap"
BONUS_NAME = "checker"
INT_MIN = -2 ** 31
INT_MAX = 2 ** 31 - 1

# Funcoes externas permitidas pelo enunciado (parte obrigatoria e bonus).
ALLOWED_FUNCS = {"read", "write", "malloc", "free", "exit"}

# Simbolos que o compilador/runtime insere sozinho (nao sao chamadas do aluno).
RUNTIME_SYMBOLS = {
    "__libc_start_main", "__cxa_finalize", "__gmon_start__",
    "_ITM_deregisterTMCloneTable", "_ITM_registerTMCloneTable",
    "__stack_chk_fail", "__stack_chk_guard", "dyld_stub_binder",
    "__libc_csu_init", "__libc_csu_fini", "_Jv_RegisterClasses",
    "_GLOBAL_OFFSET_TABLE_", "__cxa_atexit", "__dso_handle",
}
# Funcoes que o compilador PODE gerar sozinho (copias de structs, etc.).
MAYBE_COMPILER_GENERATED = {"memset", "memcpy", "memmove"}

# Limites de operacoes (folha de avaliacao classica do push_swap).
SMALL_LIMITS = {3: 3, 5: 12}
GRADE_100 = [(700, 5), (900, 4), (1100, 3), (1300, 2), (1500, 1)]
GRADE_500 = [(5500, 5), (7000, 4), (8500, 3), (10000, 2), (11500, 1)]

VALID_OPS = {"sa", "sb", "ss", "pa", "pb", "ra", "rb", "rr", "rra", "rrb", "rrr"}

CATEGORIES = [
    "Estrutura", "Makefile", "Norminette", "Requisitos do enunciado",
    "Testes funcionais", "Tratamento de erros", "Memoria", "Desempenho",
    "Bonus",
]

COMPILER_RE = re.compile(r"(^|[\s/])(cc|gcc|clang)(\s|$)")


# --------------------------------------------------------------------------- #
#  Relatorio                                                                   #
# --------------------------------------------------------------------------- #

class Report:
    def __init__(self, use_color, verbose):
        self.use_color = use_color
        self.verbose = verbose
        self.results = []        # (categoria, estado, mensagem)
        self.norm_issues = []    # (ficheiro, linha, coluna, codigo, mensagem)
        self.category = None

    def c(self, text, code):
        if not self.use_color:
            return text
        return "\033[%sm%s\033[0m" % (code, text)

    def section(self, title):
        self.category = title
        print()
        print(self.c("=" * 70, "1;34"))
        print(self.c("  " + title.upper(), "1;34"))
        print(self.c("=" * 70, "1;34"))

    def _add(self, status, msg, detail=None):
        self.results.append((self.category, status, msg))
        tag = {"OK": self.c("[OK]     ", "1;32"),
               "ERROR": self.c("[ERROR]  ", "1;31"),
               "WARNING": self.c("[WARNING]", "1;33")}[status]
        print("%s %s" % (tag, msg))
        if detail and (status != "OK" or self.verbose):
            for line in str(detail).rstrip().splitlines()[:15]:
                print("            " + self.c(line, "2"))

    def ok(self, msg, detail=None):
        self._add("OK", msg, detail)

    def error(self, msg, detail=None):
        self._add("ERROR", msg, detail)

    def warning(self, msg, detail=None):
        self._add("WARNING", msg, detail)

    def info(self, msg):
        print(self.c("          - " + msg, "36"))

    def count(self, status, category=None, exclude=None):
        return sum(1 for cat, st, _ in self.results
                   if st == status
                   and (category is None or cat == category)
                   and (exclude is None or cat not in exclude))


# --------------------------------------------------------------------------- #
#  Utilitarios                                                                 #
# --------------------------------------------------------------------------- #

class RunResult:
    def __init__(self, rc=None, out="", err="", timeout=False, missing=False,
                 elapsed=0.0):
        self.rc = rc
        self.out = out
        self.err = err
        self.timeout = timeout
        self.missing = missing
        self.elapsed = elapsed

    @property
    def crashed(self):
        return self.rc is not None and self.rc < 0

    def crash_name(self):
        try:
            return signal.Signals(-self.rc).name
        except (ValueError, TypeError):
            return "sinal %s" % (-self.rc if self.rc else "?")


def run(cmd, cwd=None, stdin_data=None, timeout=10, env=None):
    env_full = dict(os.environ)
    env_full["LC_ALL"] = "C"
    env_full["LANG"] = "C"
    if env:
        env_full.update(env)
    start = time.time()
    try:
        p = subprocess.run(
            cmd, cwd=cwd,
            input=stdin_data.encode() if isinstance(stdin_data, str) else stdin_data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, env=env_full)
        return RunResult(p.returncode, p.stdout.decode(errors="replace"),
                         p.stderr.decode(errors="replace"),
                         elapsed=time.time() - start)
    except subprocess.TimeoutExpired:
        return RunResult(timeout=True, elapsed=time.time() - start)
    except (FileNotFoundError, PermissionError, OSError):
        return RunResult(missing=True)


def find_files(root, exts):
    found = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for f in files:
            if f.endswith(exts):
                found.append(os.path.relpath(os.path.join(d, f), root))
    return sorted(found)


def fmt_args(args, limit=60):
    s = " ".join(repr(a) if (a == "" or " " in a) else a for a in args)
    return s if len(s) <= limit else s[:limit] + "..."


def rand_nums(rng, n, lo=INT_MIN, hi=INT_MAX):
    return rng.sample(range(lo, hi + 1), n)


# --------------------------------------------------------------------------- #
#  Simulador das operacoes                                                     #
# --------------------------------------------------------------------------- #

def parse_ops(stdout):
    """Devolve (lista_de_operacoes, erro)."""
    if stdout == "":
        return [], None
    if not stdout.endswith("\n"):
        return None, "a saida nao termina com '\\n'"
    ops = stdout[:-1].split("\n")
    for i, op in enumerate(ops):
        if op not in VALID_OPS:
            return None, "instrucao invalida na linha %d: %r" % (i + 1, op[:40])
    return ops, None


def simulate(nums, ops):
    a, b = deque(nums), deque()
    for op in ops:
        if op in ("sa", "ss") and len(a) > 1:
            a[0], a[1] = a[1], a[0]
        if op in ("sb", "ss") and len(b) > 1:
            b[0], b[1] = b[1], b[0]
        if op == "pa" and b:
            a.appendleft(b.popleft())
        if op == "pb" and a:
            b.appendleft(a.popleft())
        if op in ("ra", "rr") and a:
            a.rotate(-1)
        if op in ("rb", "rr") and b:
            b.rotate(-1)
        if op in ("rra", "rrr") and a:
            a.rotate(1)
        if op in ("rrb", "rrr") and b:
            b.rotate(1)
    return a, b


def verify_sort(nums, res):
    """Devolve (sucesso, mensagem, numero_de_operacoes)."""
    if res.missing:
        return False, "nao foi possivel executar o binario", 0
    if res.timeout:
        return False, "timeout (o programa nao terminou)", 0
    if res.crashed:
        return False, "o programa crashou (%s)" % res.crash_name(), 0
    if res.err.strip():
        return False, "escreveu em stderr: %r" % res.err[:60], 0
    ops, err = parse_ops(res.out)
    if err:
        return False, err, 0
    a, b = simulate(nums, ops)
    if b:
        return False, "a pilha b nao ficou vazia (%d elementos)" % len(b), len(ops)
    if list(a) != sorted(nums):
        return False, "a pilha a nao ficou ordenada", len(ops)
    return True, "%d operacoes" % len(ops), len(ops)


# --------------------------------------------------------------------------- #
#  1. Estrutura                                                                #
# --------------------------------------------------------------------------- #

def check_structure(rep, src):
    rep.section("Estrutura")
    if os.path.isfile(os.path.join(src, "Makefile")):
        rep.ok("Makefile presente na raiz")
    else:
        rep.error("Makefile em falta na raiz do repositorio")

    c_files = find_files(src, (".c",))
    h_files = find_files(src, (".h",))
    if c_files:
        rep.ok("%d ficheiro(s) .c encontrado(s)" % len(c_files))
    else:
        rep.error("Nenhum ficheiro .c encontrado")
    if h_files:
        rep.ok("%d ficheiro(s) .h encontrado(s)" % len(h_files))
    else:
        rep.error("Nenhum ficheiro .h encontrado (o enunciado pede *.h)")

    dirs = sorted({os.path.dirname(f) or "." for f in c_files + h_files})
    rep.info("Pastas com codigo: " + ", ".join(dirs))

    if os.path.isfile(os.path.join(src, "README.md")):
        rep.ok("README.md presente na raiz")
    else:
        rep.error("README.md em falta na raiz (obrigatorio nos enunciados atuais)")

    libft = os.path.join(src, "libft")
    if os.path.isdir(libft):
        if os.path.isfile(os.path.join(libft, "Makefile")):
            rep.ok("Pasta libft/ com Makefile proprio")
        else:
            rep.error("Pasta libft/ existe mas nao tem Makefile")
        try:
            mk = open(os.path.join(src, "Makefile"), errors="replace").read()
            if re.search(r"-C\s+\S*libft", mk):
                rep.ok("O Makefile principal compila a libft com o Makefile dela")
            else:
                rep.warning("Nao encontrei 'make -C libft' no Makefile principal")
        except OSError:
            pass
    elif any("libft" in d.lower() for d in dirs):
        rep.warning("Ha uma pasta parecida com libft mas nao se chama 'libft'")

    junk = []
    for d, dirnames, files in os.walk(src):
        dirnames[:] = [x for x in dirnames if x != ".git"]
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), src)
            if (f.endswith((".o", ".a", ".out", ".swp")) or f in (NAME, BONUS_NAME, ".DS_Store")
                    or rel.startswith(".vscode")):
                junk.append(rel)
        for x in dirnames:
            if x.endswith(".dSYM"):
                junk.append(os.path.relpath(os.path.join(d, x), src))
    if junk:
        rep.warning("Ficheiros gerados/lixo na pasta (confirma que nao estao no Git)",
                    "\n".join(junk[:15]))
    else:
        rep.ok("Sem binarios, objetos ou lixo na pasta")

    if os.path.isdir(os.path.join(src, ".git")) and shutil.which("git"):
        st = run(["git", "-C", src, "status", "--porcelain"])
        if st.rc == 0:
            if st.out.strip():
                rep.warning("Ha alteracoes nao commitadas: so o que esta no Git e avaliado",
                            st.out)
            else:
                rep.ok("Repositorio Git sem alteracoes pendentes")
        tracked = run(["git", "-C", src, "ls-files"])
        if tracked.rc == 0:
            tset = set(tracked.out.splitlines())
            missing = [f for f in c_files + h_files + ["Makefile", "README.md"]
                       if os.path.exists(os.path.join(src, f)) and f not in tset]
            if missing:
                rep.error("Ficheiros que existem mas NAO estao no Git", "\n".join(missing))
            tracked_junk = [f for f in tset if f.endswith((".o", ".a"))
                            or os.path.basename(f) in (NAME, BONUS_NAME)]
            if tracked_junk:
                rep.error("Binarios/objetos commitados no Git", "\n".join(tracked_junk))
    else:
        rep.warning("Pasta sem repositorio Git (nao consigo confirmar o que vai ser entregue)")


# --------------------------------------------------------------------------- #
#  2. Makefile                                                                 #
# --------------------------------------------------------------------------- #

def make(args, cwd, timeout=300):
    return run(["make"] + args, cwd=cwd, timeout=timeout)


def objects_in(root):
    return find_files(root, (".o",))


def check_makefile(rep, proj, want_bonus):
    rep.section("Makefile")
    mk_path = os.path.join(proj, "Makefile")
    if not os.path.isfile(mk_path):
        rep.error("Sem Makefile: impossivel compilar")
        return False, False
    if not shutil.which("make"):
        rep.error("O comando 'make' nao esta instalado")
        return False, False
    text = open(mk_path, errors="replace").read()

    targets = set()
    for m in re.finditer(r"^([^\s#:=][^:=#\n]*?)\s*::?(?!=)", text, re.MULTILINE):
        for t in m.group(1).split():
            targets.add(t)
    name_var = re.search(r"^\s*NAME\s*[:+?]?=\s*(\S+)", text, re.MULTILINE)
    if name_var:
        if name_var.group(1) == NAME:
            rep.ok("NAME = %s" % NAME)
        else:
            rep.warning("NAME definido como '%s' (esperado '%s')" % (name_var.group(1), NAME))
    for rule in ["$(NAME)", "all", "clean", "fclean", "re"]:
        alt = {"$(NAME)": {"$(NAME)", "${NAME}", NAME}}.get(rule, {rule})
        if targets & alt:
            rep.ok("Regra '%s' presente" % rule)
        else:
            rep.error("Regra '%s' em falta" % rule)
    has_bonus = "bonus" in targets
    if has_bonus:
        rep.ok("Regra 'bonus' presente")
    if ".PHONY" not in targets:
        rep.warning("Sem .PHONY declarado")
    if re.search(r"\$\(wildcard|\*\.c", text):
        rep.warning("O Makefile usa wildcards (*.c / $(wildcard)): muitos avaliadores nao aceitam")

    # Compilacao limpa
    make(["fclean"], proj)
    for o in objects_in(proj):
        os.remove(os.path.join(proj, o))
    binary = os.path.join(proj, NAME)
    if os.path.exists(binary):
        os.remove(binary)

    res = make([], proj)
    if res.timeout or res.rc != 0:
        rep.error("'make' falhou", (res.out + res.err)[-1500:])
        return False, has_bonus
    if os.path.isfile(binary) and os.access(binary, os.X_OK):
        rep.ok("'make' compila e gera ./%s" % NAME)
    else:
        rep.error("'make' terminou mas ./%s nao foi gerado na raiz" % NAME)
        return False, has_bonus

    # Flags (make -Bn mostra os comandos mesmo com @ no Makefile)
    dry = make(["-Bn"], proj)
    compile_lines = [l for l in dry.out.splitlines() if COMPILER_RE.search(l)]
    if compile_lines:
        missing = [f for f in ("-Wall", "-Wextra", "-Werror")
                   if not all(f in l for l in compile_lines)]
        if missing:
            rep.error("Flags em falta em pelo menos uma compilacao: " + " ".join(missing),
                      "\n".join(compile_lines[:5]))
        else:
            rep.ok("Todas as compilacoes usam -Wall -Wextra -Werror")
        if all(re.search(r"(^|[\s/])cc\s", l) for l in compile_lines):
            rep.ok("Compilador: cc")
        else:
            rep.warning("Nem todas as compilacoes usam 'cc' (o enunciado pede cc)",
                        "\n".join(compile_lines[:3]))
    else:
        rep.warning("Nao consegui ver os comandos de compilacao (make -Bn)")
    make([], proj)  # repoe o estado depois do -Bn

    # Relink
    mtime = os.path.getmtime(binary)
    time.sleep(1.1)
    res2 = make([], proj)
    relinked = (os.path.getmtime(binary) != mtime or
                any(COMPILER_RE.search(l) for l in res2.out.splitlines()))
    if relinked:
        rep.error("'make' faz relink/recompilacao sem nada ter mudado", res2.out)
    else:
        rep.ok("Sem relink num segundo 'make'")

    objs_before = objects_in(proj)

    res = make(["clean"], proj)
    left = objects_in(proj)
    if res.rc != 0:
        rep.error("'make clean' falhou", res.err)
    elif left:
        rep.error("'make clean' deixou ficheiros .o", "\n".join(left))
    else:
        rep.ok("'make clean' remove os .o")
    if res.rc == 0 and not os.path.exists(binary):
        rep.warning("'make clean' tambem apagou o binario (devia ser so o fclean)")

    res = make(["fclean"], proj)
    if res.rc != 0:
        rep.error("'make fclean' falhou", res.err)
    elif os.path.exists(binary):
        rep.error("'make fclean' nao apagou ./%s" % NAME)
    else:
        rep.ok("'make fclean' remove o binario")
    if res.rc == 0 and find_files(proj, (".a",)):
        rep.warning("'make fclean' deixou bibliotecas .a",
                    "\n".join(find_files(proj, (".a",))))

    res = make(["re"], proj)
    if res.rc == 0 and os.path.isfile(binary):
        rep.ok("'make re' recompila tudo")
    else:
        rep.error("'make re' falhou", (res.out + res.err)[-800:])
        make([], proj)

    if not objs_before:
        rep.info("Nao foram encontrados .o (os objetos podem ter outro nome/local)")
    return os.path.isfile(binary), has_bonus


# --------------------------------------------------------------------------- #
#  3. Norminette                                                               #
# --------------------------------------------------------------------------- #

def check_norminette(rep, proj):
    rep.section("Norminette")
    exe = shutil.which("norminette")
    if not exe:
        rep.warning("norminette nao instalada (pip install norminette) - verificacao saltada")
        return
    files = find_files(proj, (".c", ".h"))
    if not files:
        rep.error("Sem ficheiros para verificar")
        return
    ver = run([exe, "--version"])
    if ver.out.strip():
        rep.info(ver.out.strip().splitlines()[0])
    res = run([exe] + files, cwd=proj, timeout=600)
    if res.timeout or res.missing:
        rep.warning("A norminette nao respondeu")
        return

    status, current = {}, None
    issue_re = re.compile(r"^\s*(Error|Notice|Warning):\s*([A-Z_0-9]+)\s*"
                          r"\(line:\s*(\d+),\s*col:\s*(\d+)\):\s*(.*)$")
    clean = re.sub(r"\x1b\[[0-9;]*m", "", res.out + "\n" + res.err)
    for line in clean.splitlines():
        m = re.match(r"^(.+?):\s*(OK|Error)!?\s*$", line)
        if m and not line.lstrip().startswith(("Error:", "Notice:", "Warning:")):
            current = m.group(1).strip()
            status[current] = m.group(2)
            continue
        m = issue_re.match(line)
        if m and current:
            kind, code, ln, col, msg = m.groups()
            rep.norm_issues.append((current, int(ln), int(col), code, msg.strip(), kind))
            continue
        m = re.match(r"^\s*Error:\s*(.*)$", line)
        if m and current:
            rep.norm_issues.append((current, 0, 0, "PARSE", m.group(1).strip(), "Error"))

    for f in files:
        issues = [i for i in rep.norm_issues if i[0] == f]
        errs = [i for i in issues if i[5] == "Error"]
        notes = [i for i in issues if i[5] != "Error"]
        detail = "\n".join("linha %d, col %d: %s - %s" % (i[1], i[2], i[3], i[4])
                           for i in issues)
        if errs:
            rep.error("%s: %d erro(s) de norma" % (f, len(errs)), detail)
        elif notes:
            rep.warning("%s: %d aviso(s) de norma" % (f, len(notes)), detail)
        elif status.get(f) == "OK":
            if rep.verbose:
                rep.ok("%s" % f)
        elif f not in status:
            rep.warning("%s: a norminette nao reportou este ficheiro" % f)
    n_err = sum(1 for i in rep.norm_issues if i[5] == "Error")
    if n_err == 0:
        rep.ok("Norminette sem erros em %d ficheiro(s)" % len(files))


# --------------------------------------------------------------------------- #
#  4. Requisitos do enunciado                                                  #
# --------------------------------------------------------------------------- #

def undefined_symbols(binary):
    res = run(["nm", "-u", binary])
    if res.rc != 0:
        return None
    syms = set()
    for line in res.out.splitlines():
        parts = line.split()
        if not parts:
            continue
        name = parts[-1].split("@")[0]
        if sys.platform == "darwin" and name.startswith("_"):
            name = name[1:]
        syms.add(name)
    return syms


def check_functions(rep, binary, label, allowed):
    if not shutil.which("nm"):
        rep.warning("'nm' nao disponivel: funcoes externas nao verificadas")
        return
    syms = undefined_symbols(binary)
    if syms is None:
        rep.warning("Nao consegui ler os simbolos de %s" % label)
        return
    used, forbidden, suspicious = set(), set(), set()
    for s in syms:
        base = s
        m = re.match(r"^__(\w+)_chk$", s)
        if m:
            base = m.group(1)
        if s in RUNTIME_SYMBOLS or ("_" + s) in RUNTIME_SYMBOLS or s.lstrip("_") in {
                x.lstrip("_") for x in RUNTIME_SYMBOLS}:
            continue
        if base in allowed:
            used.add(base)
        elif base in MAYBE_COMPILER_GENERATED:
            suspicious.add(base)
        else:
            forbidden.add(s)
    rep.info("%s usa: %s" % (label, ", ".join(sorted(used)) or "(nenhuma)"))
    if forbidden:
        rep.error("%s usa funcoes externas nao permitidas: %s"
                  % (label, ", ".join(sorted(forbidden))))
    else:
        rep.ok("%s so usa funcoes externas permitidas" % label)
    if suspicious:
        rep.warning("%s referencia %s: pode ter sido gerado pelo compilador, "
                    "confirma que nao chamas diretamente" % (label, ", ".join(sorted(suspicious))))


def check_globals(rep, proj):
    if not shutil.which("nm"):
        return
    make([], proj)
    objs = objects_in(proj)
    if not objs:
        rep.warning("Sem ficheiros .o para procurar variaveis globais")
        return
    globals_found, statics_found, consts_found = [], [], []
    for o in objs:
        res = run(["nm", os.path.join(proj, o)])
        for line in res.out.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            typ, name = parts[-2], parts[-1]
            if typ in ("B", "D", "C", "G", "S"):
                globals_found.append("%s: %s" % (o, name))
            elif typ in ("b", "d") and "." not in name:
                statics_found.append("%s: %s" % (o, name))
            elif typ == "R":
                consts_found.append("%s: %s" % (o, name))
    if globals_found:
        rep.error("Variaveis globais encontradas (proibidas)", "\n".join(globals_found))
    else:
        rep.ok("Sem variaveis globais")
    if statics_found:
        rep.warning("Variaveis 'static' ao nivel do ficheiro (sao globais disfarcadas)",
                    "\n".join(statics_found))
    if consts_found:
        rep.warning("Variaveis globais 'const' encontradas: confirma se a tua versao as aceita",
                    "\n".join(consts_found))


def check_readme(rep, src):
    path = os.path.join(src, "README.md")
    if not os.path.isfile(path):
        rep.error("README.md em falta")
        return
    text = open(path, errors="replace").read()
    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    pattern = (r"^([*_])This project has been created as part of the 42 curriculum by "
               r"[^*_]+\1$")
    if re.match(pattern, first):
        rep.ok("README: primeira linha em italico com o texto exigido")
    else:
        rep.error("README: a primeira linha deve ser, em italico: "
                  "'This project has been created as part of the 42 curriculum by <login>.'",
                  "Encontrado: " + (first[:100] or "(vazio)"))
    for sec in ("Description", "Instructions", "Resources"):
        if re.search(r"^#+\s*" + sec + r"\b", text, re.MULTILINE | re.IGNORECASE):
            rep.ok("README: secao '%s' presente" % sec)
        else:
            rep.error("README: secao '%s' em falta" % sec)
    if re.search(r"\b(AI|IA|ChatGPT|Claude|LLM|artificial)\b", text, re.IGNORECASE):
        rep.ok("README: menciona o uso de IA")
    else:
        rep.warning("README: nao encontrei a descricao do uso de IA (pedida em 'Resources')")
    if re.search(r"algorithm|algoritmo|radix|turk|chunk|butterfly|sort",
                 text, re.IGNORECASE):
        rep.ok("README: parece explicar o algoritmo")
    else:
        rep.warning("README: nao encontrei explicacao/justificacao do algoritmo")


# --------------------------------------------------------------------------- #
#  5. Testes funcionais e de erros                                             #
# --------------------------------------------------------------------------- #

def ps(binary, args, timeout, stdin_data=None):
    return run([binary] + [str(a) for a in args], timeout=timeout, stdin_data=stdin_data)


def sort_test(rep, binary, label, nums, timeout, level="error", args=None, max_ops=None):
    res = ps(binary, args if args is not None else nums, timeout)
    ok, msg, nops = verify_sort(nums, res)
    if ok and max_ops is not None and nops > max_ops:
        ok, msg = False, "%d operacoes (esperado no maximo %d)" % (nops, max_ops)
    if ok:
        rep.ok("%s -> %s" % (label, msg))
    elif level == "warning":
        rep.warning("%s -> %s" % (label, msg))
    else:
        rep.error("%s -> %s" % (label, msg), "args: " + fmt_args([str(n) for n in nums]))
    return ok


def batch_test(rep, binary, label, generator, runs, timeout):
    fails, ops = [], []
    for _ in range(runs):
        nums = generator()
        ok, msg, n = verify_sort(nums, ps(binary, nums, timeout))
        ops.append(n)
        if not ok:
            fails.append("%s | args: %s" % (msg, fmt_args([str(x) for x in nums])))
    if fails:
        rep.error("%s: %d/%d falharam" % (label, len(fails), runs), "\n".join(fails[:5]))
    else:
        rep.ok("%s: %d/%d corretos (max %d ops)" % (label, runs, runs, max(ops)))


def check_functional(rep, binary, rng, timeout, quick):
    rep.section("Testes funcionais")

    res = ps(binary, [], timeout)
    if res.crashed or res.timeout:
        rep.error("Sem argumentos: o programa crashou ou bloqueou")
    elif res.out == "" and res.err == "":
        rep.ok("Sem argumentos -> nao mostra nada")
    else:
        rep.error("Sem argumentos devia nao mostrar nada",
                  "stdout=%r stderr=%r" % (res.out[:50], res.err[:50]))

    res = ps(binary, ["42"], timeout)
    if res.out == "" and res.err == "" and not res.crashed:
        rep.ok("Um numero -> nao mostra nada")
    else:
        rep.error("Um numero devia nao mostrar nada", "stdout=%r stderr=%r"
                  % (res.out[:50], res.err[:50]))

    for n in [2, 3, 5, 10, 100, 500]:
        nums = sorted(rand_nums(rng, n))
        res = ps(binary, nums, timeout)
        if res.out == "" and res.err == "" and not res.crashed and not res.timeout:
            rep.ok("Ja ordenado (n=%d) -> nenhuma operacao" % n)
        else:
            rep.error("Ja ordenado (n=%d) devia nao mostrar nada" % n,
                      "stdout=%r" % res.out[:60])

    sort_test(rep, binary, "Dois invertidos (2 1)", [2, 1], timeout)
    sort_test(rep, binary, "Dois invertidos usa no maximo 1 operacao", [2, 1], timeout,
              level="warning", max_ops=1)
    sort_test(rep, binary, "INT_MAX INT_MIN", [INT_MAX, INT_MIN], timeout)
    sort_test(rep, binary, "Extremos misturados",
              [0, INT_MAX, INT_MIN, -1, 1, INT_MAX - 1, INT_MIN + 1], timeout)

    for n in [3, 5, 10, 100, 500]:
        sort_test(rep, binary, "Ordem inversa (n=%d)" % n, list(range(n, 0, -1)), timeout)

    runs = 3 if quick else 10
    batch_test(rep, binary, "So negativos (n=10)",
               lambda: rand_nums(rng, 10, -100000, -1), runs, timeout)
    batch_test(rep, binary, "So positivos (n=20)",
               lambda: rand_nums(rng, 20, 0, 100000), runs, timeout)
    for n in range(1, 13):
        batch_test(rep, binary, "Aleatorios n=%d" % n, lambda n=n: rand_nums(rng, n),
                   runs, timeout)
    for n in [25, 50, 250]:
        batch_test(rep, binary, "Aleatorios n=%d" % n, lambda n=n: rand_nums(rng, n),
                   max(2, runs // 2), timeout)

    def almost_sorted():
        nums = sorted(rand_nums(rng, 100))
        i = rng.randrange(99)
        nums[i], nums[i + 1] = nums[i + 1], nums[i]
        return nums
    batch_test(rep, binary, "Quase ordenado (n=100, 1 troca)", almost_sorted, 3, timeout)

    # Casos ambiguos: o enunciado nao e explicito, os avaliadores divergem
    sort_test(rep, binary, "Sinal '+' aceite (+5 3)", [5, 3], timeout,
              level="warning", args=["+5", "3"])
    sort_test(rep, binary, "Zeros a esquerda aceites (007 3)", [7, 3], timeout,
              level="warning", args=["007", "3"])
    sort_test(rep, binary, "Lista numa so string (\"3 2 1\")", [3, 2, 1], timeout,
              level="warning", args=["3 2 1"])


def expect_error(rep, binary, label, args, timeout, level="error"):
    res = ps(binary, args, timeout)
    if res.crashed:
        rep.error("%s -> crash (%s)" % (label, res.crash_name()), "args: " + fmt_args(args))
        return
    if res.timeout:
        rep.error("%s -> timeout" % label, "args: " + fmt_args(args))
        return
    if res.err == "Error\n" and res.out == "":
        rep.ok("%s -> Error" % label)
        return
    if res.out == "Error\n":
        msg = "%s -> 'Error' foi escrito em stdout (deve ir para stderr)" % label
    else:
        msg = "%s -> esperado 'Error\\n' em stderr" % label
    detail = "args: %s\nstdout=%r\nstderr=%r" % (fmt_args(args), res.out[:60], res.err[:60])
    (rep.warning if level == "warning" else rep.error)(msg, detail)


def check_errors(rep, binary, timeout):
    rep.section("Tratamento de erros")
    cases = [
        ("Letra", ["a"]),
        ("Letra no meio da lista", ["1", "2", "a", "4"]),
        ("Numero com letras", ["12a"]),
        ("Letra antes do numero", ["a12"]),
        ("Numero decimal", ["1.5"]),
        ("Duplicados", ["1", "2", "1"]),
        ("Duplicados nas pontas", ["5", "3", "4", "5"]),
        ("Duplicados INT_MAX", [str(INT_MAX), "0", str(INT_MAX)]),
        ("INT_MAX + 1", [str(INT_MAX + 1)]),
        ("INT_MIN - 1", [str(INT_MIN - 1)]),
        ("Overflow no meio da lista", ["1", "99999999999", "2"]),
        ("Numero enorme", ["9" * 25]),
        ("Numero enorme negativo", ["-" + "9" * 25]),
        ("So o sinal '-'", ["-"]),
        ("So o sinal '+'", ["+"]),
        ("Sinal duplo '--5'", ["--5"]),
        ("Sinais '+-5'", ["+-5"]),
        ("Sinal no fim '5-'", ["5-"]),
    ]
    for label, args in cases:
        expect_error(rep, binary, label, args, timeout)
    # Casos com interpretacoes diferentes entre avaliadores
    expect_error(rep, binary, "String vazia \"\"", [""], timeout, level="warning")
    expect_error(rep, binary, "So espacos \"   \"", ["   "], timeout, level="warning")
    expect_error(rep, binary, "0 e -0 (duplicado numerico)", ["0", "-0"], timeout,
                 level="warning")
    expect_error(rep, binary, "1 e +1 (duplicado numerico)", ["1", "+1"], timeout,
                 level="warning")


# --------------------------------------------------------------------------- #
#  6. Memoria                                                                  #
# --------------------------------------------------------------------------- #

def valgrind_check(rep, cmd, label, stdin_data=None, timeout=120):
    vg = ["valgrind", "--leak-check=full", "--show-leak-kinds=all",
          "--errors-for-leak-kinds=none", "--error-exitcode=0"]
    res = run(vg + cmd, stdin_data=stdin_data, timeout=timeout)
    if res.timeout:
        rep.warning("%s -> valgrind demorou demasiado" % label)
        return

    def amount(kind):
        m = re.search(kind + r":\s*([\d,]+) bytes", res.err)
        return int(m.group(1).replace(",", "")) if m else 0

    lost = {k: amount(k) for k in ("definitely lost", "indirectly lost", "possibly lost")}
    reach = amount("still reachable")
    errs = re.search(r"ERROR SUMMARY:\s*(\d+)", res.err)
    n_errs = int(errs.group(1)) if errs else 0
    summary = "\n".join(l for l in res.err.splitlines()
                        if re.search(r"lost:|reachable:|ERROR SUMMARY|Invalid", l))
    if any(lost.values()):
        rep.error("%s -> leaks: %s" % (label, ", ".join(
            "%s %d B" % (k, v) for k, v in lost.items() if v)), summary)
    elif n_errs:
        rep.error("%s -> %d erro(s) de memoria (invalid read/write, etc.)" % (label, n_errs),
                  summary)
    elif reach:
        rep.warning("%s -> %d bytes 'still reachable' (memoria nao libertada a saida)"
                    % (label, reach), summary)
    else:
        rep.ok("%s -> sem leaks" % label)


def check_memory(rep, binary, rng, quick, checker=None):
    rep.section("Memoria")
    if not shutil.which("valgrind"):
        rep.warning("valgrind nao instalado - verificacao de leaks saltada "
                    "(no macOS usa 'leaks -atExit -- ./push_swap ...')")
        return
    cases = [
        ("Sem argumentos", []),
        ("Ja ordenado", ["1", "2", "3"]),
        ("3 numeros", ["3", "1", "2"]),
        ("5 numeros", [str(x) for x in rand_nums(rng, 5)]),
        ("Erro: duplicado", ["1", "2", "1"]),
        ("Erro: letra no fim", ["1", "2", "x"]),
        ("Erro: overflow", ["1", str(INT_MAX + 1)]),
    ]
    if not quick:
        cases.append(("100 numeros", [str(x) for x in rand_nums(rng, 100)]))
    for label, args in cases:
        valgrind_check(rep, [binary] + args, "push_swap: " + label)
    if checker:
        valgrind_check(rep, [checker, "3", "2", "1"], "checker: instrucoes validas",
                       stdin_data="sa\nrra\n")
        valgrind_check(rep, [checker, "3", "2", "1"], "checker: instrucao invalida",
                       stdin_data="sa\nxx\n")
        valgrind_check(rep, [checker, "1", "1"], "checker: erro de argumentos")


# --------------------------------------------------------------------------- #
#  7. Desempenho                                                               #
# --------------------------------------------------------------------------- #

def grade(value, table):
    for limit, pts in table:
        if value < limit:
            return pts
    return 0


def check_performance(rep, binary, rng, runs100, runs500, timeout, ref_checker=None):
    rep.section("Desempenho")
    points = {}

    for size, perms_base in ((3, [1, 2, 3]), (5, None)):
        limit = SMALL_LIMITS[size]
        base = perms_base or sorted(rand_nums(rng, 5, -1000, 1000))
        worst, fails = 0, []
        for perm in itertools.permutations(base):
            nums = list(perm)
            ok, msg, n = verify_sort(nums, ps(binary, nums, timeout))
            worst = max(worst, n)
            if not ok:
                fails.append("%s | %s" % (msg, fmt_args([str(x) for x in nums])))
            elif n > limit:
                fails.append("%d ops | %s" % (n, fmt_args([str(x) for x in nums])))
        total = len(list(itertools.permutations(base)))
        if fails:
            rep.error("%d numeros: %d/%d permutacoes falham (limite %d ops, pior %d)"
                      % (size, len(fails), total, limit, worst), "\n".join(fails[:5]))
        else:
            rep.ok("%d numeros: todas as %d permutacoes em <= %d ops (pior caso: %d)"
                   % (size, total, limit, worst))

    for size, runs, table in ((100, runs100, GRADE_100), (500, runs500, GRADE_500)):
        counts, fails, slow = [], [], 0
        for _ in range(runs):
            nums = rand_nums(rng, size)
            res = ps(binary, nums, timeout)
            ok, msg, n = verify_sort(nums, res)
            if not ok:
                fails.append(msg)
                continue
            counts.append(n)
            if res.elapsed > 2:
                slow += 1
            if ref_checker and len(counts) <= 3:
                cr = run([ref_checker] + [str(x) for x in nums], stdin_data=res.out,
                         timeout=timeout)
                if cr.out.strip() != "OK":
                    rep.warning("checker oficial nao confirmou OK (n=%d): %r"
                                % (size, (cr.out + cr.err).strip()[:40]))
        if fails:
            rep.error("%d numeros: %d/%d execucoes nao ordenaram" % (size, len(fails), runs),
                      "\n".join(fails[:5]))
        if not counts:
            points[size] = 0
            continue
        mx, avg, mn = max(counts), sum(counts) / len(counts), min(counts)
        pts = grade(mx, table)
        points[size] = pts
        scale = " | ".join("<%d=%dpt" % (l, p) for l, p in table)
        msg = ("%d numeros (%d execucoes): min %d, media %.0f, max %d -> %d/5 pontos"
               % (size, len(counts), mn, avg, mx, pts))
        if pts == 5:
            rep.ok(msg)
        elif pts == 0:
            rep.error(msg, "Escala (pior caso): " + scale)
        else:
            rep.warning(msg, "Escala (pior caso): " + scale)
        if slow:
            rep.warning("%d numeros: %d execucao(oes) demoraram mais de 2 s" % (size, slow))
    return points


# --------------------------------------------------------------------------- #
#  8. Bonus (checker)                                                          #
# --------------------------------------------------------------------------- #

def check_bonus(rep, proj, rng, timeout, allowed, push_swap_bin):
    rep.section("Bonus")
    res = make(["bonus"], proj)
    checker = os.path.join(proj, BONUS_NAME)
    if res.rc != 0 or not os.path.isfile(checker):
        rep.error("'make bonus' nao gerou ./%s" % BONUS_NAME, (res.out + res.err)[-800:])
        return None
    rep.ok("'make bonus' gera ./%s" % BONUS_NAME)
    mtime = os.path.getmtime(checker)
    time.sleep(1.1)
    res2 = make(["bonus"], proj)
    if os.path.getmtime(checker) != mtime or any(
            COMPILER_RE.search(l) for l in res2.out.splitlines()):
        rep.error("'make bonus' faz relink sem nada ter mudado")
    else:
        rep.ok("Sem relink num segundo 'make bonus'")
    if not find_files(proj, ("_bonus.c",)):
        rep.warning("Nao ha ficheiros *_bonus.c (o enunciado pede o sufixo _bonus)")
    check_functions(rep, checker, "checker", allowed)

    def chk(args, stdin_data):
        return run([checker] + [str(a) for a in args], stdin_data=stdin_data, timeout=timeout)

    def expect(label, args, stdin_data, out=None, err=None):
        r = chk(args, stdin_data)
        if r.crashed or r.timeout:
            rep.error("checker: %s -> crash/timeout" % label)
            return
        good = (out is None or r.out == out) and (err is None or r.err == err)
        if good:
            rep.ok("checker: %s" % label)
        else:
            rep.error("checker: %s" % label,
                      "esperado stdout=%r stderr=%r\nobtido   stdout=%r stderr=%r"
                      % (out, err, r.out[:40], r.err[:40]))

    expect("sem argumentos -> nada", [], "", out="", err="")
    expect("instrucoes que ordenam -> OK", [3, 2, 1], "sa\nrra\n", out="OK\n", err="")
    expect("instrucoes que nao ordenam -> KO", [3, 2, 1], "sa\n", out="KO\n", err="")
    expect("ja ordenado sem instrucoes -> OK", [1, 2, 3], "", out="OK\n", err="")
    expect("pilha b nao vazia -> KO", [1, 2, 3], "pb\n", out="KO\n", err="")
    expect("instrucao invalida -> Error", [3, 2, 1], "sa\nxx\n", out="", err="Error\n")
    expect("instrucao com espaco -> Error", [3, 2, 1], " sa\n", out="", err="Error\n")
    expect("argumento duplicado -> Error", [1, 2, 1], "", out="", err="Error\n")
    expect("argumento invalido -> Error", [1, "a"], "", out="", err="Error\n")
    expect("overflow -> Error", [INT_MAX + 1], "", out="", err="Error\n")

    if push_swap_bin and os.path.isfile(push_swap_bin):
        fails = 0
        for _ in range(5):
            nums = rand_nums(rng, 100)
            out = ps(push_swap_bin, nums, timeout).out
            if chk(nums, out).out != "OK\n":
                fails += 1
        if fails:
            rep.error("push_swap | checker (100 numeros): %d/5 nao deram OK" % fails)
        else:
            rep.ok("push_swap | checker (100 numeros): 5/5 OK")
    return checker


# --------------------------------------------------------------------------- #
#  Resumo                                                                      #
# --------------------------------------------------------------------------- #

LIMITATIONS = """\
Limitacoes deste avaliador (nao substitui a peer evaluation):
  - Nao e oficial: os limites (3/5/100/500 numeros), a escala de pontos e as
    funcoes permitidas seguem a folha de avaliacao classica. Confirma-os no
    TEU enunciado e ajusta as constantes no topo do script se for preciso.
  - Casos ambiguos (+5, 007, "", "3 2 1", 0 e -0) dao [WARNING], nao [ERROR]:
    os avaliadores nao concordam todos sobre eles.
  - Os testes aleatorios dao uma estimativa: 100/500 numeros com outra seed
    podem dar um pior caso maior. Usa --runs-100/--runs-500 para mais execucoes.
  - As funcoes proibidas sao detetadas com 'nm' no binario: chamadas feitas
    so dentro de codigo morto, ou funcoes da tua libft com nomes iguais aos da
    libc, podem escapar ou ser mal reportadas.
  - Variaveis globais sao detetadas nos .o; variaveis static dentro de funcoes
    nao sao reportadas (sao permitidas).
  - Leaks so sao testados com valgrind (Linux). No macOS a verificacao e saltada.
  - A Norminette so corre se estiver instalada; nao verifica o Makefile.
  - O README e avaliado por padroes de texto: nao julga a qualidade das
    explicacoes nem se o algoritmo descrito e o implementado.
  - Nao avalia o que so um humano avalia: se sabes explicar o codigo, a
    modificacao pedida durante a defesa, nem o uso indevido de IA.
"""


def summary(rep, points, has_bonus):
    rep.section("Resumo")
    total = len(rep.results)
    n_ok = rep.count("OK")
    n_err = rep.count("ERROR")
    n_warn = rep.count("WARNING")
    print("  Total de testes : %d" % total)
    print("  Aprovados       : %s" % rep.c(str(n_ok), "1;32"))
    print("  Reprovados      : %s" % rep.c(str(n_err), "1;31"))
    print("  Avisos          : %s" % rep.c(str(n_warn), "1;33"))
    print()
    print("  Por categoria:")
    for cat in CATEGORIES:
        o, e, w = (rep.count(s, cat) for s in ("OK", "ERROR", "WARNING"))
        if o + e + w:
            print("    %-26s OK %3d | ERROR %3d | WARNING %3d" % (cat, o, e, w))

    norm_err = [i for i in rep.norm_issues if i[5] == "Error"]
    print()
    print("  Erros da Norminette: %d" % len(norm_err))
    for f, ln, col, code, msg, _ in norm_err[:20]:
        print("    %s:%d:%d  %s  %s" % (f, ln, col, code, msg))
    if len(norm_err) > 20:
        print("    ... e mais %d" % (len(norm_err) - 20))

    problems = [(cat, st, msg) for cat, st, msg in rep.results
                if st != "OK" and cat not in ("Norminette", "Resumo")]
    print()
    print("  Problemas relacionados com o enunciado: %d" % len(problems))
    for cat, st, msg in problems[:30]:
        tag = rep.c("ERROR  ", "31") if st == "ERROR" else rep.c("WARNING", "33")
        print("    %s [%s] %s" % (tag, cat, msg))
    if len(problems) > 30:
        print("    ... e mais %d" % (len(problems) - 30))

    if points:
        print()
        print("  Pontuacao estimada de desempenho: 100 numeros %d/5 | 500 numeros %d/5"
              % (points.get(100, 0), points.get(500, 0)))

    mandatory_err = rep.count("ERROR", exclude={"Bonus", "Resumo"})
    bonus_err = rep.count("ERROR", "Bonus")
    print()
    if mandatory_err:
        verdict = rep.c("NAO PRONTO: %d erro(s) na parte obrigatoria. Corrige antes de "
                        "submeter." % mandatory_err, "1;31")
    elif n_warn:
        verdict = rep.c("PRONTO COM RESSALVAS: sem erros, mas revê os %d aviso(s)."
                        % n_warn, "1;33")
    else:
        verdict = rep.c("PRONTO: todos os testes automaticos passaram.", "1;32")
    print("  AVALIACAO GERAL: " + verdict)
    if has_bonus:
        if mandatory_err:
            print("  Bonus: nao sera avaliado enquanto a parte obrigatoria tiver erros.")
        elif bonus_err:
            print("  Bonus: %d erro(s)." % bonus_err)
        else:
            print("  Bonus: sem erros.")
    print()
    print(rep.c(LIMITATIONS, "2"))
    return mandatory_err


# --------------------------------------------------------------------------- #
#  Main                                                                        #
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(
        description="Avaliador automatico (nao oficial) do push_swap da 42. "
                    "Nao modifica os ficheiros do projeto.")
    ap.add_argument("--path", default=".", help="pasta do projeto (por omissao: a atual)")
    ap.add_argument("--quick", action="store_true", help="menos execucoes, mais rapido")
    ap.add_argument("--runs-100", type=int, default=None, help="execucoes com 100 numeros")
    ap.add_argument("--runs-500", type=int, default=None, help="execucoes com 500 numeros")
    ap.add_argument("--timeout", type=float, default=10, help="timeout por execucao (s)")
    ap.add_argument("--seed", type=int, default=None, help="seed dos testes aleatorios")
    ap.add_argument("--allow", action="append", default=[],
                    help="funcao externa extra permitida (repetivel), ex.: --allow ft_printf")
    ap.add_argument("--no-norm", action="store_true", help="saltar a Norminette")
    ap.add_argument("--no-valgrind", action="store_true", help="saltar os testes de leaks")
    ap.add_argument("--no-bonus", action="store_true", help="saltar o bonus")
    ap.add_argument("--no-readme", action="store_true", help="nao verificar o README")
    ap.add_argument("--keep-tmp", action="store_true", help="manter a copia temporaria")
    ap.add_argument("--no-color", action="store_true", help="sem cores")
    ap.add_argument("-v", "--verbose", action="store_true", help="mostrar mais detalhes")
    opts = ap.parse_args()

    src = os.path.abspath(opts.path)
    rep = Report(sys.stdout.isatty() and not opts.no_color, opts.verbose)
    seed = opts.seed if opts.seed is not None else random.randrange(1, 10 ** 6)
    rng = random.Random(seed)
    runs100 = opts.runs_100 or (10 if opts.quick else 50)
    runs500 = opts.runs_500 or (5 if opts.quick else 20)
    allowed = ALLOWED_FUNCS | set(opts.allow)

    print(rep.c("grademe_push_swap - avaliador nao oficial do push_swap (42)", "1"))
    print("Projeto : %s" % src)
    print("Seed    : %d  (repete com --seed %d)" % (seed, seed))
    if not os.path.isdir(src):
        print("Pasta nao encontrada.")
        return 2

    check_structure(rep, src)

    tmp = tempfile.mkdtemp(prefix="grademe_ps_")
    proj = os.path.join(tmp, "project")
    points, has_bonus = {}, False
    try:
        shutil.copytree(src, proj, symlinks=True,
                        ignore=shutil.ignore_patterns(".git"))
        for f in os.listdir(proj):  # checker oficial da intra, se existir
            p = os.path.join(proj, f)
            if f.startswith("checker_") and os.path.isfile(p):
                os.chmod(p, 0o755)
        ref_checker = next((os.path.join(proj, f) for f in ("checker_linux", "checker_Mac")
                            if os.path.isfile(os.path.join(proj, f))
                            and (f.endswith("linux") == sys.platform.startswith("linux"))),
                           None)

        built, has_bonus = check_makefile(rep, proj, not opts.no_bonus)

        if not opts.no_norm:
            check_norminette(rep, proj)

        rep.section("Requisitos do enunciado")
        binary = os.path.join(proj, NAME)
        if built:
            check_functions(rep, binary, NAME, allowed)
            check_globals(rep, proj)
        else:
            rep.error("Binario nao compilado: requisitos de codigo nao verificados")
        if not opts.no_readme:
            check_readme(rep, src)

        if built:
            check_functional(rep, binary, rng, opts.timeout, opts.quick)
            check_errors(rep, binary, opts.timeout)
            if ref_checker:
                rep.info("Checker oficial encontrado: %s" % os.path.basename(ref_checker))
            points = check_performance(rep, binary, rng, runs100, runs500,
                                       opts.timeout, ref_checker)
            checker = None
            if has_bonus and not opts.no_bonus:
                checker = check_bonus(rep, proj, rng, opts.timeout, allowed, binary)
            if not opts.no_valgrind:
                check_memory(rep, binary, rng, opts.quick, checker)
        else:
            rep.section("Testes funcionais")
            rep.error("Testes funcionais nao executados: o projeto nao compilou")
    finally:
        if opts.keep_tmp:
            print("\nCopia temporaria mantida em: %s" % proj)
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    errors = summary(rep, points, has_bonus)
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrompido.")
        sys.exit(130)
