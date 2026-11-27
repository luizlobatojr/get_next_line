/* ************************************************************************** */
/*                                                                            */
/*                                                        :::      ::::::::   */
/*   get_next_line.c                                    :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: lubatist <lubatist@student.42.fr>          +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2026/11/27 12:01:12 by lubatist          #+#    #+#             */
/*   Updated: 2026/11/27 12:33:06 by lubatist         ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */

#include "get_next_line.h"

static void	*free_stash(char **stash)
{
	if (stash && *stash)
	{
		free(*stash);
		*stash = NULL;
	}
	return (NULL);
}

static int	has_newline(const char *s)
{
	size_t	i;

	if (!s)
		return (0);
	i = 0;
	while (s[i])
	{
		if (s[i] == '\n')
			return (1);
		i++;
	}
	return (0);
}

static size_t	line_length(const char *s)
{
	size_t	i;

	i = 0;
	while (s[i] && s[i] != '\n')
		i++;
	if (s[i] == '\n')
		i++;
	return (i);
}

static char	*extract_line_and_update(char **stash)
{
	char	*line;
	char	*rem;
	size_t	len;
	size_t	rem_len;

	if (!stash || !*stash || **stash == '\0')
		free_stash(stash);
	len = line_length(*stash);
	line = dup_substr(*stash, 0, len);
	if (!line)
		free_stash(stash);
	rem_len = 0;
	while ((*stash)[len + rem_len])
		rem_len++;
	rem = NULL;
	if (rem_len > 0)
		rem = dup_substr(*stash, len, rem_len);
	free(*stash);
	*stash = rem;
	return (line);
}

char	*get_next_line(int fd)
{
	static char	*stash;
	char		*buffer;
	ssize_t		bytes_read;

	if (fd < 0 || BUFFER_SIZE <= 0)
		return (NULL);
	buffer = malloc((size_t)BUFFER_SIZE + 1);
	if (!buffer)
		return (NULL);
	bytes_read = 1;
	while (!has_newline(stash) && bytes_read > 0)
	{
		bytes_read = read(fd, buffer, BUFFER_SIZE);
		if (bytes_read < 0)
		{
			free(buffer);
			free(stash);
			return (stash = NULL);
		}
		buffer[bytes_read] = '\0';
		stash = join_and_free(stash, buffer);
		if (!stash)
			return (free(buffer), NULL);
	}
	free(buffer);
	return (extract_line_and_update(&stash));
}
/*int	main(void)
{
	int		fd;
	char	*line;

	fd = open("texto.txt", O_RDONLY);
	if (fd == -1)
		return (1);
	while ((line = get_next_line(fd)) != NULL)
	{
		printf("%s", line);
		free(line);
	}
	close(fd);
	return (0);
}*/