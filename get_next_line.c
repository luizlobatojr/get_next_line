#include "get_next_line.h"


char	*get_next_line(int fd)
{
	static char	stash[BUFFER_SIZE];
	char		buffer[BUFFER_SIZE];
	ssize_t		nbytes;
	size_t		b;

	nbytes = read(fd, buffer, BUFFER_SIZE);
	while (nbytes > 0)
	{
		b = 0;
		while (buffer[b] != '\n')
		{
			write(STDOUT, &buffer[b], 1);
			if (buffer[b] == '\0')
			{
				break ;
			}
			b++;
		}
		//if (buffer[i] != '\0' || buffer[i] != '\n')
		//{
		nbytes = 0;
		break ;
		//}
		//write(STDOUT, buffer, nbytes);
		//nbytes = read(fd, buffer, BUFFER_SIZE);
	}


	//nbytes = read(fd, buffer, BUFFER_SIZE);
	//printf("[%zd]\n", nbytes);
	while (nbytes > 0)
	{
		/*
		imprimir o stash e o buffer ate o \n

		new_line = ft_strchr(buffer, '\n');
		new_len = ft_strlen(new_line);

		write(STDOUT, new_line, new_len);

		stash = buffer depois do \n
		*/

	//	write(STDOUT, buffer, nbytes);
	//	nbytes = read(fd, buffer, BUFFER_SIZE);
		break ;
	}

	return 0;
}

int main(void)
{	
	int fd;
	char *filename = "texto.txt";

	fd = open(filename, O_RDONLY);
	if (fd == -1)
    {
		close(fd);
        perror("Erro ao abrir o ficheiro");
        return (1);
    }
printf("\n--- Linha 1--------------------\n");
	get_next_line(fd);
//printf("\n--- Linha 2--------------------\n");
//	get_next_line(fd);
printf("\n--- Fim -----------------------\n\n");
	//
	close(fd);
	return (0);
}
