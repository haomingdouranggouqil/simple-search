##### 本项目参考Groonga，Lucene，wiser等开源搜索引擎，以及《这就是搜索引擎：核心技术详解》，《自制搜索引擎》等图书，在linux环境下用C语言实现了一个简单搜索引擎，除去数据库方面调用sqlite3，解析xml文件使用expat库之外，其它功能均为自己实现，速度约为grep函数的数十倍。

#### 效果展示

- 以一个含有两万余首诗歌的文件为例，以“秦鸿”为关键词进行搜索
- ![3](https://github.com/haomingdouranggouqil/simple-search/blob/main/img/3.png)
- 输入命令 **time ./ss -q"秦鸿" now.db**
- 图为搜索引擎程序运行结果，耗时0.048s
- ![2](https://github.com/haomingdouranggouqil/simple-search/blob/main/img/2.png)
- 输入命令 **time grep "秦鸿" now.xml**
- 图为grep函数运行结果，耗时0.901s
- 结论：在此例中，搜索引擎约比grep函数提速20倍

#### 搭建环境

- 在linux上运行以下命令

  > sudo apt-get install sqlite3
  >
  > sudo apt-get install libsqlite3-dev
  >
  > sudo apt-get install libexpat-dev

- sqlite3与expat安装完毕

#### 程序构成概述

- 此搜索引擎是一个实现了简单搜索功能的程序，暂命名为simple search，简称ss，由七大块组成
- 生成xml文件：写一个Python脚本，通过语料库生成便于处理的xml格式
- 处理xml文件：将xml格式文件内容载入程序
- 生成数据库：生成存储数据和文档倒排索引的db文件
- 压缩编码：使用Golomb编码压缩数据
- 检索文档：通过倒排索引计算tf-idf值，并按得分由高到低进行输出
- 整合：将数块功能整合为一个程序
- 批量查询：数据量太多，电脑算力不够，无奈之下将数据分为多个文件，并利用shell脚本进行批量查询

#### 1.生成xml文件

- 准备的语料库为csv文件，格式为——

- | 题目  | 朝代 | 作者   | 内容    |
  | ----- | ---- | ------ | ------- |
  | title | time | author | context |

- 以汉朝诗歌数据集为例：

- ![1](https://github.com/haomingdouranggouqil/simple-search/blob/main/img/1.png)

- 我们先利用csv格式数据生成Wikipedia格式的xml方便处理

  ```python
  '''
      用csv格式数据生成类Wikipedia结构的xml文件
      @param[in] in_path 输入将处理的csv文件的路径
      @param[in] out_path 输出xml文件的路径
  '''
  def xml_generation(in_path, out_path):
      df = pd.read_csv(in_path)
      xml_str = '<mediawiki>'
      #为文档生成一个ID，从1开始，方便计数
      c = 1
      for i in df.iloc:
          xml_str += '<page>'
          xml_str += '<id>'
          xml_str += str(c)
          c += 1
          xml_str += '</id>'
          xml_str += '<title>'
          xml_str += i[0]
          xml_str += '</title>'
          xml_str += '<revison>'
          xml_str += '<text><![CDATA['
          xml_str += i[0]
          xml_str += i[1]
          xml_str += i[2]
          xml_str += i[3]
          xml_str += ']]></text>'
          xml_str += '</revison>'
          xml_str += '</page>'
      xml_str += '</mediawiki>'
      fw = open(out_path,'w',encoding='utf-8')
      fw.write(xml_str)
      fw.close()
  ```

- 然后先以汉.csv为例。

  ```python
  xml_generation('汉.csv', 'han.xml')
  ```

- 生成的类Wikipedia格式xml文件如图所示

- ![4](https://github.com/haomingdouranggouqil/simple-search/blob/main/img/4.png)

#### 2.处理xml文件

- 标签定义

  ```c
  /* poem数据集XML标签中的部分 */
  typedef enum {
    IN_DOCUMENT,          /* 以下几种状态以外的状态 */
    IN_PAGE,              /* 位于<page>标签中 */
    IN_PAGE_TITLE,        /* 位于<page>标签中的<title>标签中 */
    IN_PAGE_ID,           /* 位于<page>标签中的<id>标签中 */
    IN_PAGE_REVISION,     /* 位于<page>标签中的<revision>标签中 */
    IN_PAGE_REVISION_TEXT /* 位于<page>标签中的<revision>标签中的<text>标签中 */
  } poem_status;
  
  /* 在poem的解析器中用到的变量 */
  typedef struct {
    ss_env *env;             /* 存储着应用程序运行环境的结构体 */
    poem_status status;    /* 正在读取词条XML标签的哪一部分 */
    UT_string *title;           /* 词条标题的临时存储区 */
    UT_string *body;            /* 词条正文的临时存储区 */
    int article_count;          /* 经过解析的词条总数 */
    int max_article_count;      /* 最多要解析多少个词条 */
    add_document_callback func; /* 将解析后的文档传递给该函数 */
  } poem_parser;
  ```

- 遇到XML的起始标签时被调用的函数

  ```c
  /**
   * 遇到XML的起始标签时被调用的函数
   * @param[in] user_data poem解析器的运行环境
   * @param[in] el XML标签的名字
   * @param[in] attr XML标签的属性列表
   */
  static void XMLCALL start(void *user_data, const XML_Char *el, const XML_Char *attr[])
  {
    poem_parser *p = (poem_parser *)user_data;
    switch (p->status) 
    {
    case IN_DOCUMENT:
      if (!strcmp(el, "page")) 
      {
        p->status = IN_PAGE;
      }
      break;
    case IN_PAGE:
      if (!strcmp(el, "title")) 
      {
        p->status = IN_PAGE_TITLE;
        utstring_new(p->title);
      } 
      else if (!strcmp(el, "id")) 
      {
        p->status = IN_PAGE_ID;
      } 
      else if (!strcmp(el, "revision")) 
      {
        p->status = IN_PAGE_REVISION;
      }
      break;
    case IN_PAGE_TITLE:
    case IN_PAGE_ID:
      break;
    case IN_PAGE_REVISION:
      if (!strcmp(el, "text")) 
      {
        p->status = IN_PAGE_REVISION_TEXT;
        utstring_new(p->body);
      }
      break;
    case IN_PAGE_REVISION_TEXT:
      break;
    }
  }
  ```

- 遇到XML的结束标签时被调用的函数

  ```c
  /**
   * 遇到XML的结束标签时被调用的函数
   * @param[in] user_data poem解析器的运行环境
   * @param[in] el XML标签的名字
   */
  static void XMLCALL end(void *user_data, const XML_Char *el)
  {
    poem_parser *p = (poem_parser *)user_data;
    switch (p->status) 
    {
    case IN_DOCUMENT:
      break;
    case IN_PAGE:
      if (!strcmp(el, "page")) 
      {
        p->status = IN_DOCUMENT;
      }
      break;
    case IN_PAGE_TITLE:
      if (!strcmp(el, "title")) 
      {
        p->status = IN_PAGE;
      }
      break;
    case IN_PAGE_ID:
      if (!strcmp(el, "id")) 
      {
        p->status = IN_PAGE;
      }
      break;
    case IN_PAGE_REVISION:
      if (!strcmp(el, "revision")) 
      {
        p->status = IN_PAGE;
      }
      break;
    case IN_PAGE_REVISION_TEXT:
      if (!strcmp(el, "text"))
      {
        p->status = IN_PAGE_REVISION;
        if (p->max_article_count < 0 ||
            p->article_count < p->max_article_count) 
        {
          p->func(p->env, utstring_body(p->title), utstring_body(p->body));
        }
        utstring_free(p->title);
        utstring_free(p->body);
        p->title = NULL;
        p->body = NULL;
        p->article_count++;
      }
      break;
    }
  }
  ```

- 解析XML元素中的数据时被调用的函数

  ```c
  /**
   * 解析XML元素中的数据时被调用的函数
   * @param[in] user_data poem解析器的运行环境
   * @param[in] data 元素中的数据
   * @param[in] data_size 数据的大小
   */
  static void XMLCALL element_data(void *user_data, const XML_Char *data, int data_size)
  {
    poem_parser *p = (poem_parser *)user_data;
    switch (p->status) 
    {
    case IN_PAGE_TITLE:
      utstring_bincpy(p->title, data, data_size);
      break;
    case IN_PAGE_REVISION_TEXT:
      utstring_bincpy(p->body, data, data_size);
      break;
    default:
      /* do nothing */
      break;
    }
  }
  ```

- 加载poem的副本（XML文件），并将其内容传递给指定的函数

  ```c
  /**
   * 加载poem的副本（XML文件），并将其内容传递给指定的函数
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] path poem副本的路径
   * @param[in] func 接收env，词条标题，词条正文3个参数的回调函数（参看ss.c的223行）
   * @param[in] max_article_count 最多加载多少个词条
   * @retval 0 成功
   * @retval 1 申请内存失败
   * @retval 2 打开文件失败
   * @retval 3 加载文件失败
   * @retval 4 解析XML文件失败
   */
  int load_poem_dump(ss_env *env,
                      const char *path, add_document_callback func, int max_article_count)
  {
    FILE *fp;
    int rc = 0;
    XML_Parser xp;
    char buffer[LOAD_BUFFER_SIZE];
    poem_parser wp = {
      env,               /* 存储着应用程序运行环境的结构体 */
      IN_DOCUMENT,       /* 初始状态 */
      NULL,              /* 词条标题的临时存储区 */
      NULL,              /* 词条正文的临时存储区 */
      0,                 /* 初始化经过解析的词条总数 */
      max_article_count, /* 最多要解析多少个词条 */
      func               /* 将解析后的文档传递给该函数 */
    };
  
    if (!(xp = XML_ParserCreate("UTF-8"))) 
    {
      print_error("cannot allocate memory for parser.");
      return 1;
    }
  
    if (!(fp = fopen(path, "rb"))) 
    {
      print_error("cannot open poem dump xml file(%s).",
                  strerror(errno));
      rc = 2;
      goto exit;
    }
  
    XML_SetElementHandler(xp, start, end);
    XML_SetCharacterDataHandler(xp, element_data);
    XML_SetUserData(xp, (void *)&wp);
  
    while (1) {
      int buffer_len, done;
  
      buffer_len = (int)fread(buffer, 1, LOAD_BUFFER_SIZE, fp);
      if (ferror(fp)) 
      {
        print_error("poem dump xml file read error.");
        rc = 3;
        goto exit;
      }
      done = feof(fp);
  
      if (XML_Parse(xp, buffer, buffer_len, done) == XML_STATUS_ERROR) 
      {
        print_error("poem dump xml file parse error.");
        rc = 4;
        goto exit;
      }
  
      if (done || (max_article_count >= 0 &&
                   max_article_count <= wp.article_count)) 
      {
        break; 
      }
    }
  exit:
    if (fp) 
    {
      fclose(fp);
    }
    if (wp.title) 
    {
      utstring_free(wp.title);
    }
    if (wp.body) 
    {
      utstring_free(wp.body);
    }
    XML_ParserFree(xp);
    return rc;
  }
  ```

  







#### 3.生成数据库

- 实现方法：由于数据量大，不可能在内存上完成构建，需将硬盘作为二级存储器，先在内存上建小倒排索引，再与硬盘上存储的大倒排索引进行合并

- 首先定义一个ss_env，作为应用程序的全局配置

  ```c
  typedef struct _ss_env {
    const char *db_path;            /* 数据库的路径*/
  
    int token_len;                  /* 词元的长度。N-gram中N的取值 */
    compress_method compress;       /* 压缩倒排列表等数据的方法 */
    int enable_phrase_search;       /* 是否进行短语检索 */
  
    inverted_index_hash *ii_buffer; /* 用于更新倒排索引的缓冲区（Buffer） */
    int ii_buffer_count;            /* 用于更新倒排索引的缓冲区中的文档数 */
    int ii_buffer_update_threshold; /* 缓冲区中文档数的阈值 */
    int indexed_count;              /* 建立了索引的文档数 */
  
    /* 与sqlite3相关的配置 */
    sqlite3 *db; /* sqlite3的实例 */
    /* sqlite3的准备语句 */
    sqlite3_stmt *get_document_id_st;
    sqlite3_stmt *get_document_title_st;
    sqlite3_stmt *insert_document_st;
    sqlite3_stmt *update_document_st;
    sqlite3_stmt *get_token_id_st;
    sqlite3_stmt *get_token_st;
    sqlite3_stmt *store_token_st;
    sqlite3_stmt *get_postings_st;
    sqlite3_stmt *update_postings_st;
    sqlite3_stmt *get_settings_st;
    sqlite3_stmt *replace_settings_st;
    sqlite3_stmt *get_document_count_st;
    sqlite3_stmt *token_partial_match_st;
    sqlite3_stmt *begin_st;
    sqlite3_stmt *commit_st;
    sqlite3_stmt *rollback_st;
  } ss_env;
  ```

- 初始化程序运行环境与释放应用程序的运行环境

  ```c
  /**
   * 设定应用程序的运行环境
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] ii_buffer_update_threshold 清空（Flush）倒排索引缓冲区的阈值
   * @param[in] enable_phrase_search 是否启用短语检索
   * @param[in] db_path 数据库的路径
   * @return 错误代码
   * @retval 0 成功
   */
  static int init_env(ss_env *env,
           int ii_buffer_update_threshold, int enable_phrase_search,
           const char *db_path)
  {
    int rc;
    memset(env, 0, sizeof(ss_env));
    rc = init_database(env, db_path);
    if (!rc) 
    {
      env->token_len = N_GRAM;
      env->ii_buffer_update_threshold = ii_buffer_update_threshold;
      env->enable_phrase_search = enable_phrase_search;
    }
    return rc;
  }
  
  /**
   * 释放应用程序的运行环境
   * @param[in] env 存储着应用程序运行环境的结构体
   */
  static void fin_env(ss_env *env)
  {
    fin_database(env);
  }
  ```

- 再定义倒排列表（含有某词元的多个文档的链表）和倒排索引（含有多个词元倒排列表的数组）

  ```c
  /* 倒排列表（以文档编号和位置信息为元素的链表结构）*/
  typedef struct _postings_list {
    int document_id;             /* 文档编号 */
    UT_array *positions;         /* 位置信息的数组 */
    int positions_count;         /* 位置信息的条数 */
    struct _postings_list *next; /* 指向下一个倒排列表的指针 */
  } postings_list;
  
  /* 倒排索引（以词元编号为键，以倒排列表为值的关联数组） */
  typedef struct {
    int token_id;                 /* 词元编号（Token ID）*/
    postings_list *postings_list; /* 指向包含该词元的倒排列表的指针 */
    int docs_count;               /* 出现过该词元的文档数 */
    int positions_count;          /* 该词元在所有文档中的出现次数之和 */
    UT_hash_handle hh;            /* 用于将该结构体转化为哈希表 */
  } inverted_index_hash, inverted_index_value;
  ```

- 先编写一个函数，根据指定的文档标题获取文档编号，此函数为database相关，放到文件database.c中。

  ```c
  /**
   * 根据指定的文档标题获取文档编号
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] title 文档标题
   * @param[in] title_size 文档标题的字节数
   * @return 文档编号
   */
  int db_get_document_id(const ss_env *env,
                     const char *title, unsigned int title_size)
  {
    int rc;
    sqlite3_reset(env->get_document_id_st);
    sqlite3_bind_text(env->get_document_id_st, 1,title, title_size, SQLITE_STATIC);
    rc = sqlite3_step(env->get_document_id_st);
    if (rc == SQLITE_ROW) 
    {
      return sqlite3_column_int(env->get_document_id_st, 0);
    } 
    else 
    {
      return 0;
    }
  }
  ```

- 在此基础上可编写一个函数，将文档存储到数据库里，此函数为database相关，放到文件database.c中。

  ```c
  /**
   * 将文档添加到documents表中
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] title 文档标题
   * @param[in] title_size 文档标题的字节数
   * @param[in] body 文档正文
   * @param[in] body_size 文档正文的字节数
   */
  int db_add_document(const ss_env *env,
                  const char *title, unsigned int title_size,
                  const char *body, unsigned int body_size)
  {
    sqlite3_stmt *st;
    int rc, document_id;
  
    if ((document_id = db_get_document_id(env, title, title_size))) 
    {
      st = env->update_document_st;
      sqlite3_reset(st);
      sqlite3_bind_text(st, 1, body, body_size, SQLITE_STATIC);
      sqlite3_bind_int(st, 2, document_id);
    } 
    else 
    {
      st = env->insert_document_st;
      sqlite3_reset(st);
      sqlite3_bind_text(st, 1, title, title_size, SQLITE_STATIC);
      sqlite3_bind_text(st, 2, body, body_size, SQLITE_STATIC);
    }
  query:
    rc = sqlite3_step(st);
    switch (rc) {
    case SQLITE_BUSY:
      goto query;
    case SQLITE_ERROR:
      print_error("ERROR: %s", sqlite3_errmsg(env->db));
      break;
    case SQLITE_MISUSE:
      print_error("MISUSE: %s", sqlite3_errmsg(env->db));
      break;
    }
    return rc;
  }
  ```

- utf-8编码使用一字节到四字节，编码长度参差不齐，不便切割词元，而utf-32编码则统一为四个字节故编写两个函数，将数据在utf-8和utf-32之间互相转换，再实现其它几个与编码相关的函数，放到util.c文件中

  ```c
  /**
   * 将UTF-8的字符串转换为UTF-32的字符串
   * UTF-32的字符串存储在新分配的缓冲区中
   * @param[in] str 输入的字符串（UTF-8）
   * @param[in] str_size 输入的字符串的字节数。-1表示输入的是以NULL结尾的字符串
   * @param[out] ustr 转换后的字符串（UTF-32）。由调用方释放
   * @param[out] ustr_len 转换后的字符串的长度。调用时可将该参数设为NULL
   * @retval 0 成功
   */
  int utf8toutf32(const char *str, int str_size, UTF32Char **ustr,
              int *ustr_len)
  {
    int ulen;
    ulen = utf8_len(str, str_size);
    if (ustr_len) 
    {
      *ustr_len = ulen; 
    }
    if (!ustr) 
    {
      return 0;
    }
    if ((*ustr = malloc(sizeof(UTF32Char) * ulen))) 
    {
      UTF32Char *u;
      const char *str_end;
      for (u = *ustr, str_end = str + str_size; str < str_end;) 
      {
        if (*str >= 0) 
        {
          *u++ = *str;
          str += 1;
        } 
        else 
        {
          unsigned char s = utf8_skip_table[*str + 0x80];
          if (!s) 
          {
            abort();
          }
          /* 从n字节的UTF-8字符的首字节取出后(7 - n)个比特 */
          *u = *str & ((1 << (7 - s)) - 1);
          /* 从n字节的UTF-8字符的剩余字节序列中每次取出6个比特 */
          for (str++, s--; s--; str++) 
          {
            *u = *u << 6;
            *u |= *str & 0x3f;
          }
          u++;
        }
      }
    } 
    else 
    {
      print_error("cannot allocate memory on utf8toutf32.");
    }
    return 0;
  }
  
  /**
   * 将指定了长度的UTF-32的字符串转换为以NULL结尾的UTF-8的字符串
   * 需要在调用该函数的地方准备缓冲区，以存放作为转换结果的UTF-8的字符串
   * @param[in] ustr 输入的字符串（UTF-32）
   * @param[in] ustr_len 输入的字符串的长度。-1表示输入的是以NULL结尾的字符串
   * @param[in,out] str 存储转换后的字符串（UTF-8）的缓冲区
   *                    该缓冲区要足够大，不得小于ustr_len * MAX_UTF8_SIZE
   * @param[out] str_size 转换后的字符串的字节数。调用时可将该参数设为NULL
   * @return 转换后的UTF-8字符串
   */
  char * utf32toutf8(const UTF32Char *ustr, int ustr_len, char *str,
              int *str_size)
  {
    int sbuf_size;
    sbuf_size = uchar2utf8_size(ustr, ustr_len);
    if (str_size) 
    {
      *str_size = sbuf_size;
    }
    if (!str) 
    {
      return NULL;
    } 
    else 
    {
      char *sbuf;
      const UTF32Char *ustr_end;
      for (sbuf = str, ustr_end = ustr + ustr_len; ustr < ustr_end;
           ustr++) 
      {
        if (*ustr < 0x800) 
        {
          if (*ustr < 0x80) 
          {
            *sbuf++ = *ustr;
          } 
          else 
          {
            *sbuf++ = ((*ustr & 0x7c0) >> 6) | 0xc0;
            *sbuf++ = (*ustr & 0x3f) | 0x80;
          }
        } 
        else 
        {
          if (*ustr < 0x10000) 
          {
            *sbuf++ = ((*ustr & 0xf000) >> 12) | 0xe0;
            *sbuf++ = ((*ustr & 0xfc0) >> 6) | 0x80;
            *sbuf++ = (*ustr & 0x3f) | 0x80;
          } 
          else if (*ustr < 0x200000) 
          {
            *sbuf++ = ((*ustr & 0x1c0000) >> 18) | 0xf0;
            *sbuf++ = ((*ustr & 0x3f000) >> 12) | 0x80;
            *sbuf++ = ((*ustr & 0xfc0) >> 6) | 0x80;
            *sbuf++ = (*ustr & 0x3f) | 0x80;
          } 
          else 
          {
            abort();
          }
        }
      }
      *sbuf = '\0';
    }
    return str;
  }
  
  ```

-  为倒排索引分配存储空间并对其进行初始化

  ```c
  /**
   * 为inverted_index_value分配存储空间并对其进行初始化
   * @param[in] token_id 词元编号
   * @param[in] docs_count 包含该词元的文档数
   * @return 生成的inverted_index_value
   */
  static inverted_index_value * create_new_inverted_index(int token_id, int docs_count)
  {
    inverted_index_value *ii_entry;
  
    ii_entry = malloc(sizeof(inverted_index_value));
    if (!ii_entry) 
    {
      print_error("cannot allocate memory for an inverted index.");
      return NULL;
    }
    ii_entry->positions_count = 0;
    ii_entry->postings_list = NULL;
    ii_entry->token_id = token_id;
    ii_entry->docs_count = docs_count;
  
    return ii_entry;
  }
  ```

- 为倒排列表分配存储空间并对其进行并初始化

  ```c
  /**
   * 为倒排列表分配存储空间并对其进行并初始化
   * @param[in] document_id 文档编号
   * @return 生成的倒排列表
   */
  static postings_list * create_new_postings_list(int document_id)
  {
    postings_list *pl;
  
    pl = malloc(sizeof(postings_list));
    if (!pl) 
    {
      print_error("cannot allocate memory for a postings list.");
      return NULL;
    }
    pl->document_id = document_id;
    pl->positions_count = 1;
    utarray_new(pl->positions, &ut_int_icd);
  
    return pl;
  }
  ```

- 将输入的字符串分割为N-gram

  ```c
  /**
   * 将输入的字符串分割为N-gram
   * @param[in] ustr 输入的字符串（UTF-8）
   * @param[in] ustr_end 输入的字符串中最后一个字符的位置
   * @param[in] n N-gram中N的取值。建议将其设为大于1的值
   * @param[out] start 词元的起始位置
   * @return 分割出来的词元的长度
   */
  static int ngram_next(const UTF32Char *ustr, const UTF32Char *ustr_end,
                        unsigned int n, const UTF32Char **start)
  {
    int i;
    const UTF32Char *p;
  
    /* 读取时跳过文本开头的空格等字符 */
    for (; ustr < ustr_end && ss_is_ignored_char(*ustr); ustr++) 
    {
      //不执行操作，实际操作在for中ustr++
    }
  
    /* 不断取出最多包含n个字符的词元，直到遇到不属于索引对象的字符或到达了字符串的尾部 */
    for (i = 0, p = ustr; i < n && p < ustr_end
         && !ss_is_ignored_char(*p); i++, p++) 
    {
    }
  
    *start = ustr;
    return p - ustr;
  }
  ```

- 为传入的词元创建倒排列表

  ```c
  /**
   * 为传入的词元创建倒排列表
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] document_id 文档编号
   * @param[in] token 词元（UTF-8）
   * @param[in] token_size 词元的长度（以字节为单位）
   * @param[in] position 词元出现的位置
   * @param[in,out] postings 倒排列表的数组
   * @retval 0 成功
   * @retval -1 失败
   */
  int token_to_postings_list(ss_env *env,
                         const int document_id, const char *token,
                         const unsigned int token_size,
                         const int position,
                         inverted_index_hash **postings)
  {
    postings_list *pl;
    inverted_index_value *ii_entry;
    int token_id, token_docs_count;
    //获取词元编号，如果未分配，则分配一个新编号，已分配则返回编号
    token_id = db_get_token_id(
                 env, token, token_size, document_id, &token_docs_count);
    //如果已有小倒排索引，则获得关联到该词元编号上的倒排列表，存储到ii-entry中
    if (*postings) 
    {
      HASH_FIND_INT(*postings, &token_id, ii_entry);
    } 
    //如果没有以该词元为编号的倒排列表，先将值设为null
    else 
    {
      ii_entry = NULL;
    }
    //如果不为null，则存在关联到该词元编号上的倒排列表，先将数量加一
    if (ii_entry) 
    {
      pl = ii_entry->postings_list;
      pl->positions_count++;
    } 
    //反之则需要新建一个空的小倒排索引
    else 
    {
      ii_entry = create_new_inverted_index(token_id,
                                           document_id ? 1 : token_docs_count);
      if (!ii_entry) { return -1; }
      //将该词元加入到新的小倒排索引中
      HASH_ADD_INT(*postings, token_id, ii_entry);
      //创建仅有一个文档的倒排列表
      pl = create_new_postings_list(document_id);
      if (!pl) { return -1; }
      //将仅有一个文档的倒排列表添加到小倒排索引中
      LL_APPEND(ii_entry->postings_list, pl);
    }
    //将词元出现位置添加到存储位置信息的数组末尾 
    utarray_push_back(pl->positions, &position);
    ii_entry->positions_count++;
    return 0;
  }
  ```

- 为构成文档内容的字符串建立倒排列表的集合

  ```c
  /**
   * 为构成文档内容的字符串建立倒排列表的集合
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] document_id 文档编号。为0时表示把要查询的关键词作为处理对象
   * @param[in] text 输入的字符串
   * @param[in] text_len 输入的字符串的长度
   * @param[in] n N-gram中N的取值
   * @param[in,out] postings 倒排列表的数组（也可视作是指向小倒排索引的指针）。若传入的指针指向了NULL，
   *                         则表示要新建一个倒排列表的数组（小倒排索引）。若传入的指针指向了之前就已经存在的倒排列表的数组，
   *                         则表示要添加元素
   * @retval 0 成功
   * @retval -1 失败
   */
  int text_to_postings_lists(ss_env *env,
                         const int document_id, const UTF32Char *text,
                         const unsigned int text_len,
                         const int n, inverted_index_hash **postings)
  {
    /* FIXME: now same document update is broken. */
    int t_len, position = 0;
    const UTF32Char *t = text, *text_end = text + text_len;
    int last_t_len = 0, last_position = 0;
    const UTF32Char *last_t = NULL;
  
    inverted_index_hash *buffer_postings = NULL;
  
    for (; (t_len = ngram_next(t, text_end, n, &t)); t++, position++)
    {
      int filtered_t_len = 0, filtered_position;
      const UTF32Char *filtered_t = NULL;
  
      /* 在检索时，基本上是当position可以被n整除时才取出词元 */
      if (document_id || ((position % n == 0) && t_len >= n))
      {
          filtered_t_len = t_len;
          filtered_t = t;
          filtered_position = position;
      /* 但是，要保证最后一个词元含有n个字符 */
      }
      else if (t_len < n)
      {
          if (last_t_len && last_t)
          {
            filtered_t_len = last_t_len;
            filtered_t = last_t;
            filtered_position = last_position;
          }
          else
          {
              break;
          }
      }
  
      if (filtered_t_len && filtered_t)
      {
        int retval, t_8_size;
        char t_8[n * MAX_UTF8_SIZE];
  
        utf32toutf8(filtered_t, filtered_t_len, t_8, &t_8_size);
  
        retval = token_to_postings_list(env, document_id, t_8, t_8_size,
                                        filtered_position, &buffer_postings);
  
        if (retval)
        {
          return retval;
        }
  
          last_t_len = 0;
          last_t = NULL;
        }
        else
        {
          last_t_len = t_len;
          last_t = t;
          last_position = position;
        }
    }
  
    if (*postings)
    {
      merge_inverted_index(*postings, buffer_postings);
    }
    else
    {
      *postings = buffer_postings;
    }
  
    return 0;
  }
  ```
- 释放倒排索引

  ```c
  /**
   * 释放倒排索引
   * @param[in] ii 指向倒排索引的指针
   */
  void free_inverted_index(inverted_index_hash *ii)
  {
    inverted_index_value *cur;
    while (ii) 
    {
      cur = ii;
      HASH_DEL(ii, cur);
      if (cur->postings_list) 
      {
        free_postings_list(cur->postings_list);
      }
      free(cur);
    }
  }
  ```

- 编写函数，将错误信息输出到标准错误输出，方便debug

  ```c
  /**
   * 将错误信息输出到标准错误输出
   * @param[in] format 可以传递给函数printf的格式字符串
   * @param[in] ... 要传递给格式说明符号（format specifications）的参数
   * @return 已输出的字节数
   */
  int print_error(const char *format, ...)
  {
    int r;
    va_list l;
  
    va_start(l, format);
    vfprintf(stderr, format, l);
    r = fprintf(stderr, "\n");
    fflush(stderr);
    va_end(l);
  
    return r;
  }
  ```

- 编写函数，获取当前时间，计算其与上一次获取的当前时间的差值，并输出这两个数据，方便掌控时间

  ```c
  /**
   * 获取当前时间，计算其与上一次获取的当前时间的差值，并输出这两个数据
   */
  void print_time_diff(void)
  {
    char datetime_buf[TIMEVAL_TO_STR_BUFFER_SIZE];
    static double pre_time = 0.0;
  
    struct timeval tv;
    gettimeofday(&tv, NULL);
    timeval_to_str(&tv, datetime_buf);
    double current_time = timeval_to_double(&tv);
  
    if (pre_time) 
    {
      double time_diff = current_time - pre_time;
      print_error("[time] %s (diff %10.6lf)", datetime_buf, time_diff);
    } 
    else 
    {
      print_error("[time] %s", datetime_buf);
    }
    pre_time = current_time;
  }
  ```

- 编写函数，整合功能，将文档添加到数据库中，建立倒排索引

  ```c
  /**
   * 将文档添加到数据库中，建立倒排索引
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] title 文档标题，为NULL时将会清空缓冲区
   * @param[in] body 文档正文
   */
  static void add_document(ss_env *env, const char *title, const char *body)
  {
    if (title && body) 
    {
      UTF32Char *body32;
      int body32_len, document_id;
      unsigned int title_size, body_size;
  
      title_size = strlen(title);
      body_size = strlen(body);
  
      /* 将文档存储到数据库中并获取该文档对应的文档编号 */
      db_add_document(env, title, title_size, body, body_size);
      document_id = db_get_document_id(env, title, title_size);
  
      /* 转换文档正文的字符编码 */
      //如果转化utf-32编码成功，则————
      if (!utf8toutf32(body, body_size, &body32, &body32_len)) 
      {
        /* 为文档创建倒排列表 */
        text_to_postings_lists(env, document_id, body32, body32_len,
                               env->token_len, &env->ii_buffer);
        env->ii_buffer_count++;
        free(body32);
      }
      //如果转换编码不成功，继续且报错
      env->indexed_count++;
      print_error("count:%d title: %s", env->indexed_count, title);
    }
  
    /* 存储在缓冲区中的文档数量达到了指定的阈值时，或title = 0，即处理完所有文档时，更新存储器上的倒排索引 */
    if (env->ii_buffer && (env->ii_buffer_count > env->ii_buffer_update_threshold || !title)) 
      {
      inverted_index_hash *p;
  
      print_time_diff();
  
      /* 更新所有词元对应的倒排项 */
      for (p = env->ii_buffer; p != NULL; p = p->hh.next) 
      {
        //此函数可合并倒排索引并将结果写入数据库中
        update_postings(env, p);
      }
  
      free_inverted_index(env->ii_buffer);
      print_error("index flushed.");
      env->ii_buffer = NULL;
      env->ii_buffer_count = 0;
  
      print_time_diff();
    }
  }
  ```



#### 4.压缩编码

- 将1个比特的数据添加到缓冲区中

  ```c
  /**
   * 将1个比特的数据添加到缓冲区中
   * @param[in] buf 指向要向里面添加数据的缓冲区的指针
   * @param[in] bit 待添加的比特值。0或1
   */
  void append_buffer_bit(buffer *buf, int bit)
  {
    if (buf->curr >= buf->tail) 
    {
      if (enlarge_buffer(buf)) 
      {
        return; 
      }
    }
    if (!buf->bit) 
    {
      *buf->curr = 0; 
    }
    if (bit) 
    {
      *buf->curr |= 1 << (7 - buf->bit); 
    }
    if (++(buf->bit) == 8) 
    {
      buf->curr++; buf->bit = 0; 
    }
  }
  ```

- 扩大缓冲区的容量

  ```c
  /**
   * 扩大缓冲区的容量
   * @param[in,out] buf 指向待扩容的缓冲区的指针
   * @retval 0 成功
   * @retval 1 失败
   */
  static int enlarge_buffer(buffer *buf)
  {
    int new_size;
    char *new_head;
    new_size = (buf->tail - buf->head) * 2;
    if ((new_head = realloc(buf->head, new_size))) 
    {
      buf->curr = new_head + (buf->curr - buf->head);
      buf->tail = new_head + new_size;
      buf->head = new_head;
      return 0;
    } 
    else 
    {
      return 1;
    }
  }
  ```

- 将指定了字节数的数据添加到缓冲区中

  ```c
  /**
   * 将指定了字节数的数据添加到缓冲区中
   * @param[in] buf 指向要向里面添加数据的缓冲区的指针
   * @param[in] data 指向待添加的数据的指针
   * @param[in] data_size 待添加数据的字节数
   * @return 已添加至缓冲区中的数据的字节数
   */
  int append_buffer(buffer *buf, const void *data, unsigned int data_size)
  {
    if (buf->bit) 
    {
      buf->curr++; buf->bit = 0; 
    }
    if (buf->curr + data_size > buf->tail) 
    {
      if (enlarge_buffer(buf)) 
      {
        return 0; 
      }
    }
    if (data && data_size) 
    {
      memcpy(buf->curr, data, data_size);
      buf->curr += data_size;
    }
    return data_size;
  }
  ```

- 从数据中的指定位置读取1个比特

  ```c
  /**
   * 从数据中的指定位置读取1个比特
   * @param[in,out] buf 数据的开头
   * @param[in] buf_end 数据的结尾
   * @param[in,out] bit 从变量buf的哪个位置读取1个比特
   * @return 读取出的比特值
   */
  static inline int read_bit(const char **buf, const char *buf_end, unsigned char *bit)
  {
    int r;
    if (*buf >= buf_end) 
    {
      return -1; 
    }
    r = (**buf & *bit) ? 1 : 0;
    *bit >>= 1;
    if (!*bit) 
    {
      *bit = 0x80;
      (*buf)++;
    }
    return r;
  }
  ```

- 将倒排列表转换成字节序列

  ```c
  /**
   * 将倒排列表转换成字节序列
   * @param[in] postings 倒排列表
   * @param[in] postings_len 倒排列表中的元素数
   * @param[out] postings_e 转换后的倒排列表
   * @retval 0 成功
   */
  static int encode_postings_none(const postings_list *postings,
                       const int postings_len,
                       buffer *postings_e)
  {
    const postings_list *p;
    LL_FOREACH(postings, p) 
    {
      int *pos = NULL;
      append_buffer(postings_e, (void *)&p->document_id, sizeof(int));
      append_buffer(postings_e, (void *)&p->positions_count, sizeof(int));
      while ((pos = (int *)utarray_next(p->positions, pos))) 
      {
        append_buffer(postings_e, (void *)pos, sizeof(int));
      }
    }
    return 0;
  }
  ```

- 从字节序列中还原出倒排列表

  ```c
  /**
   * 从字节序列中还原出倒排列表
   * @param[in] postings_e 待还原的倒排列表（字节序列）
   * @param[in] postings_e_size 待还原的倒排列表（字节序列）中的元素数
   * @param[out] postings 还原后的倒排列表
   * @param[out] postings_len 还原后的倒排列表中的元素数
   * @retval 0 成功
   *
   */
  static int decode_postings_none(const char *postings_e, int postings_e_size,
                       postings_list **postings, int *postings_len)
  {
    const int *p, *pend;
  
    *postings = NULL;
    *postings_len = 0;
    for (p = (const int *)postings_e,
         pend = (const int *)(postings_e + postings_e_size); p < pend;) 
    {
      postings_list *pl;
      int document_id, positions_count;
  
      document_id = *(p++);
      positions_count = *(p++);
      if ((pl = malloc(sizeof(postings_list)))) 
      {
        int i;
        pl->document_id = document_id;
        pl->positions_count = positions_count;
        utarray_new(pl->positions, &ut_int_icd);
        LL_APPEND(*postings, pl);
        (*postings_len)++;
  
        /* 解码 */
        for (i = 0; i < positions_count; i++) 
        {
          utarray_push_back(pl->positions, p);
          p++;
        }
      } 
      else 
      {
        p += positions_count;
      }
    }
    return 0;
  }
  ```

- 用Golomb编码对1个数值进行编码

  ```c
  /**
   * 用Golomb编码对1个数值进行编码
   * @param[in] m Golomb编码中的参数m
   * @param[in] b Golomb编码中的参数b。ceil(log2(m))
   * @param[in] t pow2(b) - m
   * @param[in] n 待编码的数值
   * @param[in] buf 编码后的数据
   */
  static inline void golomb_encoding(int m, int b, int t, int n, buffer *buf)
  {
    int i;
    /* encode (n / m) with unary code */
    for (i = n / m; i; i--) 
    {
      append_buffer_bit(buf, 1); 
    }
    append_buffer_bit(buf, 0);
    /* encode (n % m) */
    if (m > 1) 
    {
      int r = n % m;
      if (r < t) 
      {
        for (i = 1 << (b - 2); i; i >>= 1) 
        {
          append_buffer_bit(buf, r & i);
        }
      } 
      else 
      {
        r += t;
        for (i = 1 << (b - 1); i; i >>= 1) 
        {
          append_buffer_bit(buf, r & i);
        }
      }
    }
  }
  ```

- 根据Golomb编码中的参数m，计算出编码和解码过程中所需的参数b和参数t

  ```c
  /**
   * 根据Golomb编码中的参数m，计算出编码和解码过程中所需的参数b和参数t
   * @param[in] m Golomb编码中的参数m
   * @param[out] b Golomb编码中的参数b。ceil(log2(m))
   * @param[out] t pow2(b) - m
   */
  static void calc_golomb_params(int m, int *b, int *t)
  {
    int l;
    assert(m > 0);
    for (*b = 0, l = 1; m > l; (*b)++, l <<= 1) {}
    *t = l - m;
  }
  ```

- 对倒排列表进行Golomb编码

  ```c
  /**
   * 对倒排列表进行Golomb编码
   * @param[in] documents_count 文档总数
   * @param[in] postings 待编码的倒排列表
   * @param[in] postings_len 待编码的倒排列表中的元素数
   * @param[in] postings_e 编码后的倒排列表
   * @retval 0 成功
   */
  static int encode_postings_golomb(int documents_count,
                         const postings_list *postings, const int postings_len,
                         buffer *postings_e)
  {
    const postings_list *p;
  
    append_buffer(postings_e, &postings_len, sizeof(int));
    if (postings && postings_len) 
    {
      int m, b, t;
      m = documents_count / postings_len;
      append_buffer(postings_e, &m, sizeof(int));
      calc_golomb_params(m, &b, &t);
      {
        int pre_document_id = 0;
  
        LL_FOREACH(postings, p) 
        {
          int gap = p->document_id - pre_document_id - 1;
          golomb_encoding(m, b, t, gap, postings_e);
          pre_document_id = p->document_id;
        }
      }
      append_buffer(postings_e, NULL, 0);
    }
    LL_FOREACH(postings, p) 
    {
      append_buffer(postings_e, &p->positions_count, sizeof(int));
      if (p->positions && p->positions_count) 
      {
        const int *pp;
        int mp, bp, tp, pre_position = -1;
  
        pp = (const int *)utarray_back(p->positions);
        mp = (*pp + 1) / p->positions_count;
        calc_golomb_params(mp, &bp, &tp);
        append_buffer(postings_e, &mp, sizeof(int));
        pp = NULL;
        while ((pp = (const int *)utarray_next(p->positions, pp))) 
        {
          int gap = *pp - pre_position - 1;
          golomb_encoding(mp, bp, tp, gap, postings_e);
          pre_position = *pp;
        }
        append_buffer(postings_e, NULL, 0);
      }
    }
    return 0;
  }
  ```

- 用Golomb编码对1个数值进行解码

  ```c
  /**
   * 用Golomb编码对1个数值进行解码
   * @param[in] m Golomb编码中的参数m
   * @param[in] b Golomb编码中的参数b。ceil(log2(m))
   * @param[in] t pow2(b) - m
   * @param[in,out] buf 待解码的数据
   * @param[in] buf_end 待解码数据的结尾
   * @param[in,out] bit 待解码数据的起始比特
   * @return 解码后的数值
   */
  static inline int golomb_decoding(int m, int b, int t,
                  const char **buf, const char *buf_end, unsigned char *bit)
  {
    int n = 0;
  
    /* decode (n / m) with unary code */
    while (read_bit(buf, buf_end, bit) == 1) 
    {
      n += m;
    }
    /* decode (n % m) */
    if (m > 1) 
    {
      int i, r = 0;
      for (i = 0; i < b - 1; i++) 
      {
        int z = read_bit(buf, buf_end, bit);
        if (z == -1) 
        {
          print_error("invalid golomb code"); 
          break; 
        }
        r = (r << 1) | z;
      }
      if (r >= t) 
      {
        int z = read_bit(buf, buf_end, bit);
        if (z == -1) 
        {
          print_error("invalid golomb code");
        } 
        else 
        {
          r = (r << 1) | z;
          r -= t;
        }
      }
      n += r;
    }
    return n;
  }
  ```

- 对经过Golomb编码的倒排列表进行解码

  ```c
  /**
   * 对经过Golomb编码的倒排列表进行解码
   * @param[in] postings_e 经过Golomb编码的倒排列表
   * @param[in] postings_e_size 经过Golomb编码的倒排列表中的元素数
   * @param[out] postings 解码后的倒排列表
   * @param[out] postings_len 解码后的倒排列表中的元素数
   * @retval 0 成功
   */
  static int decode_postings_golomb(const char *postings_e, int postings_e_size,
                         postings_list **postings, int *postings_len)
  {
    const char *pend;
    unsigned char bit;
  
    pend = postings_e + postings_e_size;
    bit = 0x80;
    *postings = NULL;
    *postings_len = 0;
    {
      int i, docs_count;
      postings_list *pl;
      {
        int m, b, t, pre_document_id = 0;
  
        docs_count = *((int *)postings_e);
        postings_e += sizeof(int);
        m = *((int *)postings_e);
        postings_e += sizeof(int);
        calc_golomb_params(m, &b, &t);
        for (i = 0; i < docs_count; i++) 
        {
          int gap = golomb_decoding(m, b, t, &postings_e, pend, &bit);
          if ((pl = malloc(sizeof(postings_list)))) 
          {
            pl->document_id = pre_document_id + gap + 1;
            utarray_new(pl->positions, &ut_int_icd);
            LL_APPEND(*postings, pl);
            (*postings_len)++;
            pre_document_id = pl->document_id;
          } 
          else 
          {
            print_error("memory allocation failed.");
          }
        }
      }
      if (bit != 0x80) 
      {
        postings_e++; bit = 0x80; 
      }
      for (i = 0, pl = *postings; i < docs_count; i++, pl = pl->next) 
      {
        int j, mp, bp, tp, position = -1;
  
        pl->positions_count = *((int *)postings_e);
        postings_e += sizeof(int);
        mp = *((int *)postings_e);
        postings_e += sizeof(int);
        calc_golomb_params(mp, &bp, &tp);
        for (j = 0; j < pl->positions_count; j++) 
        {
          int gap = golomb_decoding(mp, bp, tp, &postings_e, pend, &bit);
          position += gap + 1;
          utarray_push_back(pl->positions, &position);
        }
        if (bit != 0x80) 
        {
          postings_e++; bit = 0x80; 
        }
      }
    }
    return 0;
  }
  ```

- 对倒排列表进行还原或解码

  ```c
  /**
   * 对倒排列表进行还原或解码
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] postings_e 待还原或解码前的倒排列表
   * @param[in] postings_e_size 待还原或解码前的倒排列表中的元素数
   * @param[out] postings 还原或解码后的倒排列表
   * @param[out] postings_len 还原或解码后的倒排列表中的元素数
   * @retval 0 成功
   */
  static int decode_postings(const ss_env *env,
                  const char *postings_e, int postings_e_size,
                  postings_list **postings, int *postings_len)
  {
    switch (env->compress) 
    {
    case compress_none:
      return decode_postings_none(postings_e, postings_e_size,
                                  postings, postings_len);
    case compress_golomb:
      return decode_postings_golomb(postings_e, postings_e_size,
                                    postings, postings_len);
    default:
      abort();
    }
  }
  ```

- 对倒排列表进行转换或编码

  ```c
  /**
   * 对倒排列表进行转换或编码
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] postings 待转换或编码前的倒排列表
   * @param[in] postings_len 待转换或编码前的倒排列表中的元素数
   * @param[out] postings_e 转换或编码后的倒排列表
   * @retval 0 成功
   */
  static int encode_postings(const ss_env *env,
                  const postings_list *postings, const int postings_len,
                  buffer *postings_e)
  {
    switch (env->compress) 
    {
    case compress_none:
      return encode_postings_none(postings, postings_len, postings_e);
    case compress_golomb:
      return encode_postings_golomb(db_get_document_count(env),
                                    postings, postings_len, postings_e);
    default:
      abort();
    }
  }
  ```

- 从数据库中获取关联到指定词元上的倒排列表

  ```c
  /**
   * 从数据库中获取关联到指定词元上的倒排列表
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] token_id 词元编号
   * @param[out] postings 获取到的倒排列表
   * @param[out] postings_len 获取到的倒排列表中的元素数
   * @retval 0 成功
   * @retval -1 失败
   */
  int fetch_postings(const ss_env *env, const int token_id,
                 postings_list **postings, int *postings_len)
  {
    char *postings_e;
    int postings_e_size, docs_count, rc;
  
    rc = db_get_postings(env, token_id, &docs_count, (void **)&postings_e,
                         &postings_e_size);
    if (!rc && postings_e_size) 
    {
      /* 只有当倒排列表非空时，才进行解码 */
      int decoded_len;
      if (decode_postings(env, postings_e, postings_e_size, postings,
                          &decoded_len)) 
      {
        print_error("postings list decode error");
        rc = -1;
      } 
      else if 
      (docs_count != decoded_len) 
      {
        print_error("postings list decode error: stored:%d decoded:%d.\n",
                    *postings_len, decoded_len);
        rc = -1;
      }
      if (postings_len)   
      {
        *postings_len = decoded_len; 
      }
    } 
    else 
    {
      *postings = NULL;
      if (postings_len) 
      {
        *postings_len = 0; 
      }
    }
    return rc;
  }
  ```
  
- 将内存上（小倒排索引中）的倒排列表与存储器上的倒排列表合并后存储到数据库中

  ```c
  /**
   * 将内存上（小倒排索引中）的倒排列表与存储器上的倒排列表合并后存储到数据库中
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] p 含有倒排列表的倒排索引中的索引项
   */
  void update_postings(const ss_env *env, inverted_index_value *p)
  {
    int old_postings_len;
    postings_list *old_postings;
  
    //首先取出存储器上作为合并源的倒排列表
    if (!fetch_postings(env, p->token_id, &old_postings,
                        &old_postings_len)) 
    {
      //申请一块缓冲区
      buffer *buf;
      if (old_postings_len) 
      {
        p->postings_list = merge_postings(old_postings, p->postings_list);
        p->docs_count += old_postings_len;
      }
      if ((buf = alloc_buffer())) 
      {
        //将内存上的倒排索引转换为字节
        encode_postings(env, p->postings_list, p->docs_count, buf);
        //将转换为字节的倒排索引存储到存储器中
        db_update_postings(env, p->token_id, p->docs_count,
                           BUFFER_PTR(buf), BUFFER_SIZE(buf));
        free_buffer(buf);
      }
    } 
    //取不出待合并的倒排列表，报错
    else 
    {
      print_error("cannot fetch old postings list of token(%d) for update.",
                  p->token_id);
    }
  }
  ```

#### 5.检索文档

- 从查询字符串中提取出词元的信息

  ```c
  /**
   * 从查询字符串中提取出词元的信息
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] text 查询字符串
   * @param[in] text_len 查询字符串的长度
   * @param[in] n N-gram中N的取值
   * @param[in,out] query_tokens 按词元编号存储位置信息序列的关联数组
   *                             若传入的是指向NULL的指针，则新建一个关联数组
   * @retval 0 成功
   * @retval -1 失败
   */
  int split_query_to_tokens(ss_env *env,
                        const UTF32Char *text,
                        const unsigned int text_len,
                        const int n, query_token_hash **query_tokens)
  {
    //第二个参数为0，代表不需要使用文档编号
    return text_to_postings_lists(env,
                                  0, /* 将document_id设为0 */
                                  text, text_len, n,
                                  (inverted_index_hash **)query_tokens);
  }
  ```


- 比较出现过词元a和词元b的文档数

  ```c
  /**
   * 比较出现过词元a和词元b的文档数
   * @param[in] a 词元a的数据
   * @param[in] b 词元b的数据
   * @return 文档数的大小关系
   */
  static int query_token_value_docs_count_desc_sort(query_token_value *a,
                                         query_token_value *b)
  {
    return b->docs_count - a->docs_count;
  }
  ```

- 根据词元编号从数据库中获取倒排列表

  ```c
  int db_get_postings(const ss_env *env, int token_id,
                  int *docs_count, void **postings, int *postings_size)
  {
    int rc;
    sqlite3_reset(env->get_postings_st);
    sqlite3_bind_int(env->get_postings_st, 1, token_id);
    rc = sqlite3_step(env->get_postings_st);
    if (rc == SQLITE_ROW) 
    {
      if (docs_count) 
      {
        *docs_count = sqlite3_column_int(env->get_postings_st, 0);
      }
      if (postings) 
      {
        *postings = (void *)sqlite3_column_blob(env->get_postings_st, 1);
      }
      if (postings_size) 
      {
        *postings_size = (int)sqlite3_column_bytes(env->get_postings_st, 1);
      }
      rc = 0;
    } 
    else 
    {
      if (docs_count) 
      {
        *docs_count = 0; 
        }
      if (postings) 
      {
        *postings = NULL; 
      }
      if (postings_size) 
      {
        *postings_size = 0; 
      }
      if (rc == SQLITE_DONE) 
      {
        rc = 0; 
      } /* no record found */
    }
    return rc;
  }
  ```
- 从数据库中获取关联到指定词元上的倒排列表

  ```c
  /**
   * 从数据库中获取关联到指定词元上的倒排列表
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] token_id 词元编号
   * @param[out] postings 获取到的倒排列表
   * @param[out] postings_len 获取到的倒排列表中的元素数
   * @retval 0 成功
   * @retval -1 失败
   */
  int fetch_postings(const ss_env *env, const int token_id,
                 postings_list **postings, int *postings_len)
  {
    char *postings_e;
    int postings_e_size, docs_count, rc;
  
    rc = db_get_postings(env, token_id, &docs_count, (void **)&postings_e,
                         &postings_e_size);
    if (!rc && postings_e_size) 
    {
      /* 只有当倒排列表非空时，才进行解码 */
      int decoded_len;
      if (decode_postings(env, postings_e, postings_e_size, postings,
                          &decoded_len)) 
      {
        print_error("postings list decode error");
        rc = -1;
      } 
      else if 
      (docs_count != decoded_len) 
      {
        print_error("postings list decode error: stored:%d decoded:%d.\n",
                    *postings_len, decoded_len);
        rc = -1;
      }
      if (postings_len)   
      {
        *postings_len = decoded_len; 
      }
    } 
    else 
    {
      *postings = NULL;
      if (postings_len) 
      {
        *postings_len = 0; 
      }
    }
    return rc;
  }
  ```

- 进行短语检索

  ```c
  /**
   * 进行短语检索
   * @param[in] query_tokens 从查询中提取出的词元信息
   * @param[in] doc_cursors 用于检索文档的游标的集合
   * @return 检索出的短语数
   */
  static int search_phrase(const query_token_hash *query_tokens,
                doc_search_cursor *doc_cursors)
  {
    int n_positions = 0;
    const query_token_value *qt;
    phrase_search_cursor *cursors;
  
    /* 获取查询中词元的总数 */
    for (qt = query_tokens; qt; qt = qt->hh.next) 
    {
      n_positions += qt->positions_count;
    }
    //分配结构体作为短语检索的游标
    if ((cursors = (phrase_search_cursor *)malloc(sizeof(
                     phrase_search_cursor) * n_positions))) 
    {
      int i, phrase_count = 0;
      phrase_search_cursor *cur;
      /* 初始化游标 */
      for (i = 0, cur = cursors, qt = query_tokens; qt;
           i++, qt = qt->hh.next) 
      {
        int *pos = NULL;
        while ((pos = (int *)utarray_next(qt->postings_list->positions,
                                          pos))) 
        {
          //将词元在查询中出现的位置存储到base中
          cur->base = *pos;
          cur->positions = doc_cursors[i].current->positions;
          //将词元在文档中出现的位置存储到current中
          cur->current = (int *)utarray_front(cur->positions);
          cur++;
        }
      }
      /* 检索短语 */
      while (cursors[0].current) 
      {
        int rel_position, next_rel_position;
        //得到词元偏移量
        rel_position = next_rel_position = *cursors[0].current - cursors[0].base;
        /* 对于除词元A以外的词元，不断地向后读取其出现位置，直到其偏移量不小于词元A的偏移量为止 */
        for (cur = cursors + 1, i = 1; i < n_positions; cur++, i++) 
        {
          for (; cur->current
               && (*cur->current - cur->base) < rel_position;
               cur->current = (int *)utarray_next(cur->positions, cur->current)) {}
          if (!cur->current) 
          { 
            goto exit; 
          }
  
          /* 对于除词元A以外的词元，若其偏移量不等于A的偏移量，就退出循环 */
          if ((*cur->current - cur->base) != rel_position) 
          {
            next_rel_position = *cur->current - cur->base;
            break;
          }
        }
        if (next_rel_position > rel_position) 
        {
          /* 不断向后读取，直到词元A的偏移量不小于next_rel_position为止 */
          while (cursors[0].current &&
                 (*cursors[0].current - cursors[0].base) < next_rel_position) 
          {
            cursors[0].current = (int *)utarray_next(cursors[0].positions, cursors[0].current);
          }
        } 
        else 
        {
          /* 找到了短语,计数加一，并将游标指向下一个词元A出现位置 */
          phrase_count++;
          cursors->current = (int *)utarray_next(cursors->positions, cursors->current);
        }
      }
  exit:
      free(cursors);
      return phrase_count;
    }
    return 0;
  }
  ```

- 用TF-IDF计算得分

  ```c
  /**
   * 用TF-IDF计算得分
   * @param[in] query_tokens 查询
   * @param[in] doc_cursors 用于文档检索的游标的集合
   * @param[in] n_query_tokens 查询中的词元数
   * @param[in] indexed_count 建立过索引的文档总数
   * @return 得分
   */
  static double calc_tf_idf(
    const query_token_hash *query_tokens,
    doc_search_cursor *doc_cursors, const int n_query_tokens,
    const int indexed_count)
  {
    int i;
    const query_token_value *qt;
    doc_search_cursor *dcur;
    double score = 0;
    for (qt = query_tokens, dcur = doc_cursors, i = 0;
         i < n_query_tokens;
         qt = qt->hh.next, dcur++, i++) 
    {
      double idf = log2((double)indexed_count / qt->docs_count);
      score += (double)dcur->current->positions_count * idf;
    }
    return score;
  }
  ```

- 将文档添加到检索结果中

  ```c
  /**
   * 将文档添加到检索结果中
   * @param[in] results 指向检索结果的指针
   * @param[in] document_id 要添加的文档的编号
   * @param[in] score 得分
   */
  static void add_search_result(search_results **results, const int document_id,
                    const double score)
  {
    search_results *r;
    if (*results) 
    {
      HASH_FIND_INT(*results, &document_id, r);
    } 
    else 
    {
      r = NULL;
    }
    if (!r) 
    {
      if ((r = malloc(sizeof(search_results)))) 
      {
        r->document_id = document_id;
        r->score = 0;
        HASH_ADD_INT(*results, document_id, r);
      }
    }
    if (r) 
    {
      r->score += score;
    }
  }
  ```

- 释放倒排列表

  ```c
  /**
   * 释放倒排列表
   * @param[in] pl 待释放的倒排列表中的首元素
   */
  void free_postings_list(postings_list *pl)
  {
    postings_list *a, *a2;
    LL_FOREACH_SAFE(pl, a, a2) 
    {
      if (a->positions) 
      {
        utarray_free(a->positions);
      }
      LL_DELETE(pl, a);
      free(a);
    }
  }
  ```

- 释放词元的出现位置列表

  ```c
  /**
   * 释放词元的出现位置列表
   * @param[in] pl 待释放的出现位置列表的首元素
   */
  void free_token_positions_list(token_positions_list *list)
  {
    free_postings_list((postings_list *)list);
  }
  ```

- 根据得分比较两条检索结果

  ```c
  /**
   * 根据得分比较两条检索结果
   * @param[in] a 检索结果a的数据
   * @param[in] b 检索结果b的数据
   * @return 得分的大小关系
   */
  static int search_results_score_desc_sort(search_results *a, search_results *b)
  {
    return (b->score > a->score) ? 1 : (b->score < a->score) ? -1 : 0;
  }
  ```

- 检索文档

  ```c
  /**
   * 检索文档
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in,out] results 检索结果
   * @param[in] tokens 从查询中提取出的词元信息
   */
  void search_docs(ss_env *env, search_results **results,
              query_token_hash *tokens)
  {
    int n_tokens;
    doc_search_cursor *cursors;
    //如果没有词元则直接返回
    if (!tokens) { return; }
  
    /* 取出词元，并按照文档频率的升序对tokens排序 */
    HASH_SORT(tokens, query_token_value_docs_count_desc_sort);
  
    /* 初始化 */
    n_tokens = HASH_COUNT(tokens);
  
    //为每个词元申请了一块内存地址空间，用来存储指向文档的游标
    if (n_tokens &&
        (cursors = (doc_search_cursor *)calloc(
                     sizeof(doc_search_cursor), n_tokens))) 
    {
      int i;
      doc_search_cursor *cur;
      query_token_value *token;
      //将词元从集合中逐一取出
      for (i = 0, token = tokens; token; i++, token = token->hh.next) 
      {
        //如果无对应编号，说明数据库中不存在，跳转到exit中断检索
        if (!token->token_id) 
        {
          /* 当前的token在构建索引的过程中从未出现过 */
          goto exit;
        }
        //反正则有对应编号，即数据中存在该词元，通过调用fetch_postings函数获取该词元对应倒排列表
        if (fetch_postings(env, token->token_id,
                           &cursors[i].documents, NULL)) 
        {
          print_error("decode postings error!: %d\n", token->token_id);
          goto exit;
        }
        if (!cursors[i].documents) 
        {
          /* 虽然当前的token存在，但是由于更新或删除导致其倒排列表为空 */
          goto exit;
        }
        //为该词元设置游标，指向第一个文档
        cursors[i].current = cursors[i].documents;
      }
      //词元游标指定完毕
      while (cursors[0].current) 
      {
        int doc_id, next_doc_id = 0;
        /* 将拥有文档最少的词元称作A */
        doc_id = cursors[0].current->document_id;      
        /* 对于除词元A以外的词元，不断获取其下一个document_id，直到当前的document_id不小于词元A的document_id为止 */
        for (cur = cursors + 1, i = 1; i < n_tokens; cur++, i++) 
        {
          while (cur->current && cur->current->document_id < doc_id) 
          {
            cur->current = cur->current->next;
          }
          //到了倒排列表末尾，中断检索
          if (!cur->current) 
          { 
            goto exit; 
          }      
          /* 对于除词元A以外的词元，如果其document_id不等于词元A的document_id，*/
          /* 那么就将这个document_id设定为next_doc_id */
          if (cur->current->document_id != doc_id) 
          {
            next_doc_id = cur->current->document_id;
            break;
          }
        }
        if (next_doc_id > 0) 
        {
          /* 不断获取A的下一个document_id，直到其当前的document_id不小于next_doc_id为止 */
          while (cursors[0].current
                 && cursors[0].current->document_id < next_doc_id) 
          {
            cursors[0].current = cursors[0].current->next;
          }
        } 
        else 
        {
          int phrase_count = -1;
          if (env->enable_phrase_search) 
          {
            phrase_count = search_phrase(tokens, cursors);
          }
          if (phrase_count) 
          {
            double score = calc_tf_idf(tokens, cursors, n_tokens,
                                       env->indexed_count);
            add_search_result(results, doc_id, score);
          }
          cursors[0].current = cursors[0].current->next;
        }
      }
  exit:
      for (i = 0; i < n_tokens; i++) 
      {
        if (cursors[i].documents) 
        {
          free_token_positions_list(cursors[i].documents);
        }
      }
      free(cursors);
    }
    free_inverted_index(tokens);
  
    HASH_SORT(*results, search_results_score_desc_sort);
  }
  ```

- 根据指定的文档编号获取文档标题

  ```c
  /**
   * 根据指定的文档编号获取文档标题
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] document_id 文档编号
   * @param[out] title 文档标题
   * @param[out] title_size 文档标题的字节数
   */
  int db_get_document_title(const ss_env *env, int document_id,
                        const char **title, int *title_size)
  {
    int rc;
  
    sqlite3_reset(env->get_document_title_st);
    sqlite3_bind_int(env->get_document_title_st, 1, document_id);
  
    rc = sqlite3_step(env->get_document_title_st);
    if (rc == SQLITE_ROW) 
    {
      if (title) 
      {
        *title = (const char *)sqlite3_column_text(env->get_document_title_st,
                 0);
      }
      printf("%s", title);
      if (title_size) 
      {
        *title_size = (int)sqlite3_column_bytes(env->get_document_title_st,
                                                0);
      }
    }
    return 0;
  }
  ```

- 打印检索结果

  ```c
  /**
   * 打印检索结果
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] results 检索结果
   */
  void print_search_results(ss_env *env, search_results *results)
  {
    int num_search_results;
  
    if (!results) { return; }
    num_search_results = HASH_COUNT(results);
  
    while (results) {
      int title_len;
      const char *title;
      search_results *r;
  
      r = results;
      HASH_DEL(results, r);
      db_get_document_title(env, r->document_id, &title, &title_len);
      printf("document_id: %d title: %.*s score: %lf\n",
             r->document_id, title_len, title, r->score);
      free(r);
    }
  
    printf("Total %u documents are found!\n", num_search_results);
  }
  ```

- 获取与指定的查询字符串部分匹配的词元的列表

  ```c
  /**
   * 获取与指定的查询字符串部分匹配的词元的列表
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] query 查询字符串
   * @param[in] query_len 查询字符串的长度
   * @param[out] tokens 词元的列表
   */
  int token_partial_match(const wiser_env *env, const char *query,
                      int query_len,
                      UT_array *tokens)
  {
    int rc;
    sqlite3_reset(env->token_partial_match_st);
    sqlite3_bind_text(env->token_partial_match_st, 1, query, query_len,
                      SQLITE_TRANSIENT);
    while ((rc = sqlite3_step(env->token_partial_match_st)) ==
           SQLITE_ROW) 
    {
      char *title = (char *)sqlite3_column_text(env->token_partial_match_st,
                    0);
      utarray_push_back(tokens, &title);                  
    }
    return 0;
  }
  ```

  

- 进行全文检索

  ```c
  /**
   * 进行全文检索
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] query 查询
   */
  void search(ss_env *env, const char *query)
  {
    int query32_len;
    UTF32Char *query32;
    //首先将查询字符转化为32以便分割词元
    if (!utf8toutf32(query, strlen(query), &query32, &query32_len)) 
    {
      search_results *results = NULL;
      if (query32_len < env->token_len) 
      {
        char **p;
          UT_array *partial_tokens;
  
          utarray_new(partial_tokens, &ut_str_icd);
          token_partial_match(env, query, strlen(query), partial_tokens);
          for (p = (char **)utarray_front(partial_tokens); p;
               p = (char **)utarray_next(partial_tokens, p)) {
            inverted_index_hash *query_postings = NULL;
            token_to_postings_list(env, 0, *p, strlen(*p), 0, &query_postings);
            search_docs(env, &results, query_postings);
          }
          utarray_free(partial_tokens);
      } 
      else 
      {
        //分割查询字符为词元，存储在query_tokens中，调用search_docs函数检索文档
        query_token_hash *query_tokens = NULL;
        split_query_to_tokens(env, query32, query32_len, env->token_len, &query_tokens);
        search_docs(env, &results, query_tokens);
      }
      //打印查询结果
      print_search_results(env, results);
  
      free(query32);
    }
  }
  ```

#### 6.整合

- 更新存储在数据库中的配置信息

  ```c
  /**
   * 更新存储在数据库中的配置信息
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] key 配置项的名称
   * @param[in] key_size 配置项名称的字节数
   * @param[in] value 配置项的取值
   * @param[in] value_size 配置项取值的字节数
   */
  int db_replace_settings(const ss_env *env, const char *key,
                      int key_size,
                      const char *value, int value_size)
  {
    int rc;
    sqlite3_reset(env->replace_settings_st);
    sqlite3_bind_text(env->replace_settings_st, 1,
                      key, key_size, SQLITE_STATIC);
    sqlite3_bind_text(env->replace_settings_st, 2,
                      value, value_size, SQLITE_STATIC);
  query:
    rc = sqlite3_step(env->replace_settings_st);
  
    switch (rc) 
    {
    case SQLITE_BUSY:
      goto query;
    case SQLITE_ERROR:
      print_error("ERROR: %s", sqlite3_errmsg(env->db));
      break;
    case SQLITE_MISUSE:
      print_error("MISUSE: %s", sqlite3_errmsg(env->db));
      break;
    }
    return rc;
  }
  ```

- 进行全文检索

  ```c
  /**
   * 进行全文检索
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] method 压缩倒排列表的方法
   * @param[in] method_size 压缩方法名称的字节数
   */
  static void parse_compress_method(ss_env *env, const char *method,
                        int method_size)
  {
    if (method && method_size < 0) { method_size = strlen(method); }
    if (!method || !method_size
        || MEMSTRCMP(method, method_size, "golomb")) 
    {
      env->compress = compress_golomb;
    } 
    else if (MEMSTRCMP(method, method_size, "none")) 
    {
      env->compress = compress_none;
    } 
    else 
    {
      print_error("invalid compress method(%.*s). use golomb instead.",
                  method_size, method);
      env->compress = compress_golomb;
    }
    switch (env->compress) 
    {
    case compress_none:
      db_replace_settings(env,
                          "compress_method", sizeof("compress_method") - 1,
                          "none", sizeof("none") - 1);
      break;
    case compress_golomb:
      db_replace_settings(env,
                          "compress_method", sizeof("compress_method") - 1,
                          "golomb", sizeof("golomb") - 1);
      break;
    }
  }
  ```

- 从数据库中获取配置信息

  ```c
  /**
   * 从数据库中获取配置信息
   * @param[in] env 存储着应用程序运行环境的结构体
   * @param[in] key 配置项的名称
   * @param[in] key_size 配置项名称的字节数
   * @param[out] value 配置项的取值
   * @param[out] value_size 配置项取值的字节数
   */
  int db_get_settings(const ss_env *env, const char *key, int key_size,
                  const char **value, int *value_size)
  {
    int rc;
  
    sqlite3_reset(env->get_settings_st);
    sqlite3_bind_text(env->get_settings_st, 1,
                      key, key_size, SQLITE_STATIC);
    rc = sqlite3_step(env->get_settings_st);
    if (rc == SQLITE_ROW) 
    {
      if (value) 
      {
        *value = (const char *)sqlite3_column_text(env->get_settings_st, 0);
      }
      if (value_size) 
      {
        *value_size = (int)sqlite3_column_bytes(env->get_settings_st, 0);
      }
    }
    return 0;
  }
  ```

- 获取已添加到数据库中的文档数

  ```c
  /**
   * 获取已添加到数据库中的文档数
   * @param[in] env 存储着应用程序运行环境的结构体
   */
  int db_get_document_count(const ss_env *env)
  {
    int rc;
  
    sqlite3_reset(env->get_document_count_st);
    rc = sqlite3_step(env->get_document_count_st);
    if (rc == SQLITE_ROW) 
    {
      return sqlite3_column_int(env->get_document_count_st, 0);
    } 
    else 
    {
      return -1;
    }
  }
  ```

- 事务函数

  ```c
  /**
   * 开启事务
   * @param[in] env 存储着应用程序运行环境的结构体
   */
  int begin(const ss_env *env)
  {
    return sqlite3_step(env->begin_st);
  }
  
  /**
   * 提交事务
   * @param[in] env 存储着应用程序运行环境的结构体
   */
  int commit(const ss_env *env)
  {
    return sqlite3_step(env->commit_st);
  }
  
  /**
   * 回滚事务
   * @param[in] env 存储着应用程序运行环境的结构体
   */
  int rollback(const ss_env *env)
  {
    return sqlite3_step(env->rollback_st);
  }
  ```

- 主体程序

  ```c
  /**
   * 入口
   * @param[in] argc 参数的个数
   * @param[in] argv 参数指针的数组
   */
  int main(int argc, char *argv[])
  {
    ss_env env;
    extern int optind;
    int max_index_count = -1; /* 不限制参与索引构建的文档数量 */
    int ii_buffer_update_threshold = DEFAULT_II_BUFFER_UPDATE_THRESHOLD;
    int enable_phrase_search = TRUE;
    const char *compress_method_str = NULL, *poem_dump_file = NULL,
                *query = NULL;
    /* 解析参数字符串 */
    {
      int ch;
      extern int opterr;
      extern char *optarg;
  
      while ((ch = getopt(argc, argv, "c:x:q:m:t:s")) != -1) 
      {
        switch (ch) 
        {
        case 'c':
          compress_method_str = optarg;
          break;
        case 'x':
          poem_dump_file = optarg;
          break;
        case 'q':
          query = optarg;
          break;
        case 'm':
          max_index_count = atoi(optarg);
          break;
        case 't':
          ii_buffer_update_threshold = atoi(optarg);
          break;
        case 's':
          enable_phrase_search = FALSE;
          break;
        }
      }
    }
  
    /* 使用解析过的参数运行ss */
    if (argc != optind + 1) 
    {
      printf(
        "usage: %s [options] db_file\n"
        "\n"
        "选项:\n"
        "  -c compress_method            : 指定压缩方式\n"
        "  -x poem_dump_xml              : 需要生成数据库的xml数据集\n"
        "  -q search_query               : 查询关键词\n"
        "  -m max_index_count            : 载入文档的最大数量\n"
        "  -t ii_buffer_update_threshold : 缓冲区暂存的词条总数\n"
        "  -s                            : 不使用词组搜索\n"
        "\n"
        "压缩方式:\n"
        "  none   : 无.\n"
        "  golomb : 默认使用Golomb-Rice.\n",
        argv[0]);
      return -1;
    }
  
    /* 在构建索引时，若指定的数据库已存在则报错 */
    {
      struct stat st;
      if (poem_dump_file && !stat(argv[optind], &st)) 
      {
        printf("%s is already exists.\n", argv[optind]);
        return -2;
      }
    }
  
    {
      int rc = init_env(&env, ii_buffer_update_threshold, enable_phrase_search,
                    argv[optind]);
      if (!rc) {
        print_time_diff();
  
        /* 加载poem的词条数据 */
        if (poem_dump_file) 
        {
          parse_compress_method(&env, compress_method_str, -1);
          begin(&env);
          if (!load_poem_dump(&env, poem_dump_file, add_document,
                                   max_index_count)) 
          {
            /* 清空缓冲区 */
            add_document(&env, NULL, NULL);
            commit(&env);
          } 
          else 
          {
            rollback(&env);
          }
        }
  
        /* 进行检索 */
        if (query) 
        {
          int cm_size;
          const char *cm;
          db_get_settings(&env,
                          "compress_method", sizeof("compress_method") - 1,
                          &cm, &cm_size);
          parse_compress_method(&env, cm, cm_size);
          env.indexed_count = db_get_document_count(&env);
          search(&env, query);
        }
        fin_env(&env);
  
        print_time_diff();
      }
      return rc;
    }
  }
  ```

#### 7.批量查询

- 首先将八十余万首诗歌以万为单位生成八十六个xml文件

  ```py
  import pandas as pd
  
  import os
  
  xml_str = '<mediawiki>'
  c = 1
  f = 1
  for filepath,dirnames,filenames in os.walk(r'Poetry-master'):
      for file in filenames:
          path = 'Poetry-master/' + file
          print(path)
          df = pd.read_csv(path)
          for i in df.iloc:
              xml_str += '<page>'
              xml_str += '<id>'
              xml_str += str(c)
              c += 1
              xml_str += '</id>'
              xml_str += '<title>'
              xml_str += '题目：'
              xml_str += str(i[0])
              xml_str += '\n'
              xml_str += '年代：'
              xml_str += str(i[1])
              xml_str += '\n'
              xml_str += '作者：'
              xml_str += str(i[2])
              xml_str += '\n'
              xml_str += '正文：'
              xml_str += str(i[3])
              xml_str += '\n'
              xml_str += '</title>'
              xml_str += '<revision>'
              xml_str += '<text><![CDATA['
              xml_str += str(i[0])
              xml_str += str(i[1])
              xml_str += str(i[2])
              xml_str += str(i[3])
              xml_str += ']]></text>'
              xml_str += '</revision>'
              xml_str += '</page>'
              if c > 10000:
                  xml_str += '</mediawiki>'
                  fw = open(str(f) + '.xml','w',encoding='utf-8')
                  f += 1
                  fw.write(xml_str)
                  fw.close()
                  xml_str = '<mediawiki>'
                  c = 1
  
  if c != 1:
      xml_str += '</mediawiki>'
      fw = open(str(f) + '.xml','w',encoding='utf-8')
      fw.write(xml_str)
      fw.close()
  ```

- 用Python生成训练脚本

  ```python
  s = '#!bin/sh\n'
  for i in range(1,87):
  
      s += './ss -x '
      s += str(i)
      s += '.xml '
      s += str(i)
      s += '.db;\n'
  
  fw = open('train.sh','w')
  fw.write(s)
  fw.close()
  ```

- 生成查询脚本

  ```python
  s = '#!bin/sh\n'
  
  query = '添雪斋'
  for i in range(1,87):
  
      s += './ss -q '
      s += "'"
      s += query
      s += "' "
      s += str(i)
      s += '.db;\n'
  
  fw = open('query.sh','w',encoding='utf-8')
  fw.write(s)
  fw.close()
  ```

  

