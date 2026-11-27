/* ************************************************************************** */
/*                                                                            */
/*                                                        :::      ::::::::   */
/*   get_next_line_utils.c                              :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: lubatist <lubatist@student.42.fr>          +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2026/11/27 12:00:51 by lubatist          #+#    #+#             */
/*   Updated: 2026/11/27 12:23:08 by lubatist         ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */

#include "get_next_line.h"

static size_t	str_len(const char *s)
{
	size_t	i;

	if (!s)
		return (0);
	i = 0;
	while (s[i])
		i++;
	return (i);
}

char	*ft_strchr(const char *s, int c)
{
	if (!s)
		return (NULL);
	while (*s)
	{
		if (*s == (char)c)
			return ((char *)s);
		s++;
	}
	if ((char)c == '\0')
		return ((char *)s);
	return (NULL);
}

char	*dup_substr(const char *s, size_t start, size_t len)
{
	char	*out;
	size_t	i;

	out = malloc(len + 1);
	if (!out)
		return (NULL);
	i = 0;
	while (i < len)
	{
		out[i] = s[start + i];
		i++;
	}
	out[i] = '\0';
	return (out);
}

char	*join_and_free(char *stash, const char *buf)
{
	char	*out;
	size_t	len1;
	size_t	len2;
	size_t	i;
	size_t	j;

	len1 = str_len(stash);
	len2 = str_len(buf);
	out = malloc(len1 + len2 + 1);
	if (!out)
		return (free(stash), NULL);
	i = 0;
	while (i < len1)
	{
		out[i] = stash[i];
		i++;
	}
	j = 0;
	while (j < len2)
		out[i++] = buf[j++];
	out[i] = '\0';
	return (free(stash), out);
}
