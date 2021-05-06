#ifndef __DATABASE_H__
#define __DATABASE_H__

#include <sqlite3.h>

#include "ss.h"

int init_database(ss_env *env, const char *db_path);
void fin_database(ss_env *env);
int db_get_document_id(const ss_env *env,
                       const char *title, unsigned int title_size);
int db_get_document_title(const ss_env *env, int document_id,
                          const char **const title, int *title_size);
int db_add_document(const ss_env *env,
                    const char *title, unsigned int title_size,
                    const char *body, unsigned int body_size);
int db_get_token_id(const ss_env *env,
                    const char *str, unsigned int str_size, int insert,
                    int *docs_count);
int db_get_token(const ss_env *env,
                 const int token_id,
                 const char **const token, int *token_size);
int db_get_postings(const ss_env *env, int token_id,
                    int *docs_count, void **postings, int *postings_size);
int db_update_postings(const ss_env *env, int token_id,
                       int docs_count,
                       void *postings, int postings_size);
int db_get_settings(const ss_env *env, const char *key,
                    int key_size,
                    const char **value, int *value_size);
int db_replace_settings(const ss_env *env, const char *key,
                        int key_size,
                        const char *value, int value_size);
int db_get_document_count(const ss_env *env);
int token_partial_match(const ss_env *env, const char *query,
                        int query_len, UT_array *token_ids);
int begin(const ss_env *env);
int commit(const ss_env *env);
int rollback(const ss_env *env);

#endif /* __DATABASE_H__ */
