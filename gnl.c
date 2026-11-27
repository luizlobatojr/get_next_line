
#include "get_next_line.h"

char	*get_next_line(int fd)
{
	static char	*stash;
	char		*buffer;
	char		*line;
	char		*temp;
	int			bytes;
	int			i;
	int			j;
	int			len;

	/* Verifica se o descritor e o BUFFER_SIZE sao validos */
	if (fd < 0 || BUFFER_SIZE <= 0)
		return (NULL);

	/* Reserva memoria para receber os blocos de leitura */
	buffer = malloc(BUFFER_SIZE + 1);
	if (!buffer)
		return (NULL);

	/*
	 * Enquanto nao encontrar uma quebra de linha,
	 * continua lendo o arquivo em blocos.
	 */
	bytes = 1;
	while (bytes > 0)
	{
		i = 0;
		while (stash && stash[i] && stash[i] != '\n')
			i++;
		if (stash && stash[i] == '\n')
			break ;
		bytes = read(fd, buffer, BUFFER_SIZE);
		if (bytes < 0)
			return (free(buffer), NULL);
		buffer[bytes] = '\0';

		/*
		 * Calcula o tamanho do stash atual.
		 */
		len = 0;
		while (stash && stash[len])
			len++;

		/*
		 * Reserva espaco para juntar:
		 * stash antigo + dados novos.
		 */
		temp = malloc(len + bytes + 1);
		if (!temp)
			return (free(buffer), NULL);

		/* Copia o conteudo antigo */
		i = 0;
		while (i < len)
		{
			temp[i] = stash[i];
			i++;
		}

		/* Adiciona os novos caracteres */
		j = 0;
		while (j < bytes)
			temp[i++] = buffer[j++];

		temp[i] = '\0';

		/* Atualiza o stash */
		free(stash);
		stash = temp;
	}
	free(buffer);

	/* Se nao existe mais conteudo, termina */
	if (!stash || !*stash)
		return (free(stash), stash = NULL, NULL);

	/*
	 * Descobre o tamanho da linha.
	 * Inclui '\n' quando existir.
	 */
	i = 0;
	while (stash[i] && stash[i] != '\n')
		i++;
	if (stash[i] == '\n')
		i++;
	len = i;

	/* Reserva memoria para devolver a linha */
	line = malloc(len + 1);
	if (!line)
		return (NULL);

	/* Copia a linha para a variavel line */
	i = 0;
	while (i < len)
	{
		line[i] = stash[i];
		i++;
	}
	line[i] = '\0';

	/*
	 * Guarda no stash tudo o que ficou
	 * depois da linha devolvida.
	 */
	j = 0;
	while (stash[i + j])
		j++;

	temp = malloc(j + 1);
	if (!temp)
		return (free(line), NULL);

	i = 0;
	while (i < j)
	{
		temp[i] = stash[len + i];
		i++;
	}
	temp[i] = '\0';

	free(stash);
	stash = temp;

	/* Devolve a linha encontrada */
	if (!*stash)
	{
		free(stash);
		stash = NULL;
	}
	return (line);
}
