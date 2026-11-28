/* ************************************************************************** */
/*                                                                            */
/*                                                        :::      ::::::::   */
/*   get_next_line.c                                    :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: lubatist <lubatist@student.42.fr>          +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2026/11/28 10:21:17 by lubatist          #+#    #+#             */
/*   Updated: 2026/11/28 10:23:16 by lubatist         ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */

#include "get_next_line.h"
#include <stdio.h>

char	*read_stash(int fd, char *stash)
{
	char	*buffer;
	int		bytes_read;

	buffer = malloc(sizeof(char) * BUFFER_SIZE + 1);
	if (!buffer)
		return (NULL);
	bytes_read = 1;
	while (!ft_strchr(stash, '\n') && bytes_read != 0)
	{
		bytes_read = read(fd, buffer, BUFFER_SIZE);
		if (bytes_read == -1)
		{
			free(stash);
			free(buffer);
			return (NULL);
		}
		buffer[bytes_read] = '\0';
		stash = ft_strjoin(stash, buffer);
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
	if (!stash || *stash == '\0')
		return (free(stash), stash = NULL, NULL);
	if (ft_strchr(stash, '\n'))
		out = ft_substr(stash, 0, ft_strchr(stash, '\n') - stash + 1);
	else
		out = ft_substr(stash, 0, ft_strchr(stash, '\0') - stash);
	tmp = stash;
	if (ft_strchr(stash, '\n') && *(ft_strchr(stash, '\n') + 1))
		stash = ft_substr(stash, ft_strchr(stash, '\n') - stash + 1,
				ft_strchr(stash, '\0') - ft_strchr(stash, '\n'));
	else
		stash = NULL;
	return (free(tmp), out);
}

/*
int main(void)
{
	int fd;

	fd = open("texto.txt", O_RDONLY);
	get_next_line(fd);
	// printf("--------------------------------------\n");
	get_next_line(fd);
	// printf("--------------------------------------\n");
	get_next_line(fd);
	// printf("--------------------------------------\n");
	// get_next_line(fd);
	// printf("--------------------------------------\n");
	// get_next_line(fd);
	close(fd);
}*/