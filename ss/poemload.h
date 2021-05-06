#ifndef __POEMLOAD_H__
#define __POEMLOAD_H__

#include "ss.h"

typedef void (*add_document_callback)(ss_env *env,
                                      const char *title,
                                      const char *body);

int load_poem_dump(ss_env *env, const char *path,
                        add_document_callback func, int max_article_count);

#endif /* __POEMLOAD_H__ */
