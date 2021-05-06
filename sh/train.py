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
