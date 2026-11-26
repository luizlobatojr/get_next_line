#include "get_next_line.h"

size_t	ft_strlen(const char *s)
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

char	*ft_substr(const char *s, size_t start, size_t len)
{
	char	*sub;
	size_t	i;

	sub = malloc(len + 1);
	if (!sub)
		return (NULL);
	i = 0;
	while (i < len && s[start + i])
	{
		sub[i] = s[start + i];
		i++;
	}
	sub[i] = '\0';
	return (sub);
}

char	*ft_strjoin_free(char *s1, const char *s2)
{
	char	*joined;
	size_t	len1;
	size_t	len2;
	size_t	i;

	len1 = ft_strlen(s1);
	len2 = ft_strlen(s2);
	joined = malloc(len1 + len2 + 1);
	if (!joined)
	{
		free(s1);
		return (NULL);
	}
	i = 0;
	while (i < len1)
	{
		joined[i] = s1[i];
		i++;
	}
	i = 0;
	while (i < len2)
	{
		joined[len1 + i] = s2[i];
		i++;
	}
	joined[len1 + len2] = '\0';
	free(s1);
	return (joined);
}
