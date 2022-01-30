from crypt import methods
from ntpath import join
from subprocess import Popen, PIPE


def query(query_name):
    process = Popen('bash query.sh ' + query_name, shell = True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()

    content = stdout.decode('utf-8', errors='ignore').split('\n')

    title = []
    era = []
    name = []
    poem = []
    for line in content:
        if '题目' in line:
            title.append(line.split(':')[-1])
        elif '年代' in line:
            era.append(line.split(':')[-1])
        elif '作者' in line:
            name.append(line.split(':')[-1])
        elif '正文' in line:
            poem.append(line.split(':')[-1])
        else:
            pass

    element = list(zip(title, era, name, poem))
    html = "".join(['<div><h3>{}</h3>{}<br>{}<br>{}<br></div>'.format(i[0], i[1], i[2], i[3]) for i in element])
    return html

from flask import Flask, render_template, request, redirect

app = Flask(__name__)


@app.route("/", methods=["POST", "GET"])
def index():
    return render_template('Index.html')

@app.route("/result", methods=["POST", "GET"])
def result():
    key = request.form.get('key')
    if len(key) > 1:
        return query(key)
    else:
        return render_template('Index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)



