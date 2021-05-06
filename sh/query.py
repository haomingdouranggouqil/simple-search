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
