s = '#!bin/sh\n'

query = '$1'
for i in range(1,87):

    s += './ss -q '
    s += query
    s += ' '
    s += str(i)
    s += '.db;\n'

fw = open('query.sh','w',encoding='utf-8')
fw.write(s)
fw.close()
