import pandas as pd

import os

xml_str = '<mediawiki>'
c = 1
f = 1
for filepath,dirnames,filenames in os.walk(r'corpus'):
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
