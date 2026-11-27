/* ************************************************************************** */
/*                                                                            */
/*                                                        :::      ::::::::   */
/*   get_next_line.c                                    :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: lubatist <lubatist@student.42.fr>          +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2026/11/27 13:25:50 by lubatist          #+#    #+#             */
/*   Updated: 2026/11/27 14:25:08 by lubatist         ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */

# include "get_next_line.h"
# include <fcntl.h>
# include <stdio.h>

static char *read_stash(int fd, char *stash)
{
	char	*buffer;
	int		bytes_read;

	buffer = malloc(sizeof(char) * BUFFER_SIZE + 1);
	if (!buffer)
	{
		return (NULL);
	}
	bytes_read = 1;
	while (!ft_strchr(stash, '\n') && bytes_read != 0)
	{
		bytes_read = read(fd, buffer, BUFFER_SIZE);
		if (bytes_read == -1)
		{
			free(stash);
			free(buffer);
			return ( NULL);
		}
		buffer[bytes_read] = '\0';

		printf("stach antes: %s\n", stash);
		
		stash = ft_strjoin(stash, buffer);
		
		//printf("stach depois: %s\n", stash);
		//printf("buffer : %s", buffer);
		//printf("buffer:[%s] | stash:[%s]\n", buffer, stash);

	}
	free(buffer);
	return (stash);
}

char	*get_next_line(int fd)
{
	static char	*stash;
	char		*out;
	char		*tmp;

	if (fd < 0 || BUFFER_SIZE <= 0)
		return (NULL);
	stash = read_stash(fd, stash);
	return (0);
}

int	main(void)
{
	int	fd;
	
	fd = open("texto.txt", O_RDONLY);
	get_next_line(fd);
	// printf("--------------------------------------\n");
	// get_next_line(fd);
	// printf("--------------------------------------\n");
	// get_next_line(fd);
	// printf("--------------------------------------\n");
	// get_next_line(fd);
	// printf("--------------------------------------\n");
	// get_next_line(fd);
	// printf("--------------------------------------\n");
	// get_next_line(fd);
	// printf("--------------------------------------\n");
	// get_next_line(fd);
	// printf("--------------------------------------\n");
	// get_next_line(fd);
	close (fd);
}