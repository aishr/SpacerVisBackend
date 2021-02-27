"""Style guide: use underscore for all variable and function names"""
import requests
import sys
if sys.version_info.major < 3:
    raise Exception("User error: This application only supports Python 3, so please use python3 instead of python!")
import json
from flask import Flask, request, abort
from flask_cors import CORS
import tempfile
import argparse
import os

from subprocess import PIPE, STDOUT, Popen, run, check_output
from app.settings import DATABASE, MEDIA, PROSEBASEURL, options_for_visualization
from app.utils.utils import *
import app.utils.trace_parsing as ms
import re
import hashlib
import traceback

app = Flask(__name__)
app.config.from_object(__name__)
CORS(app)

parser = argparse.ArgumentParser(description='Run Spacer Server')
parser.add_argument("-z3", "--z3", required=True, action="store", dest="z3_path", help="path to z3 python")
args = parser.parse_args()

def update_status():
    exps_list = []
    for exp in query_db('select * from exp where done is 0'):
        r = {}
        for k in exp.keys():
            r[k] = exp[k]
        exps_list.append(exp["exp_name"])

    # NHAM: Legacy code. Now we will check if the parsing is done using the parser itself
    # for exp in exps_list:
    #     print("EXP:", exp)
    #     is_running = check_if_process_running(exp)
    #     if not is_running:
    #         get_db().execute('UPDATE exp SET done = 1 WHERE name = ?', (exp,));

    #commit
    get_db().commit()

def pooling():
    update_status()
    return fetch_exps()

def fetch_options(): 
    test_args = [args.z3_path, "-p"]
    output = check_output(test_args)
    lines = output.decode("utf-8").split("\n")
    result = parse_options(lines)
    return json.dumps(result)

def parse_options(lines):
    result = []
    prefix = ""
    for line in lines:
        if re.search("\[module\]\ ([a-zA-Z]+).*", line):
            prefix = re.findall("\[module\]\ ([a-zA-Z]+).*", line)[0]
        elif re.search("\ \ \ \ (.*)\ \((.*)\)\ \(default:\ (.*)\)", line):
            details = re.findall("\ \ \ \ (.*)\ \((.*)\)\ \(default:\ (.*)\)", line)[0]
            result.append({"name": (prefix if prefix == "" else prefix + ".") + details[0], "type": details[1], "default": details[2], "dash": True if prefix == "" else False})
    return result

def learn_transformation():
    request_params = request.get_json()
    exp_name = request_params.get('expName', '')
    exp_folder = os.path.join(MEDIA, exp_name)
    # learn transformation doesnt use exprMap(Lemmas) so we should give it empty object
    spacer_instance = {"Id": exp_name, "Lemmas": {}}
    inputOutputExamples = request_params.get('inputOutputExamples', '')
    params = request_params.get('params', '')
    tType = request_params.get('type', '')
    body = {
        'instance': exp_name,
        'inputOutputExamples': inputOutputExamples,
        'spacerInstance': json.dumps(spacer_instance)
    }

    print("spacer_instance", json.dumps(spacer_instance, indent=4)[:200])
    print("input output examples", json.dumps(inputOutputExamples, indent = 2))
    if tType == "replace":
        body['params'] = params 
        url = os.path.join(PROSEBASEURL, 'variables', 'replace')
        response = requests.post(url, json=body)
        if response.status_code != 200:
            abort(response.status_code)

        return json.dumps({'status': "success", "response": response.json()})
    
        
    declare_statements = get_declare_statements(exp_folder)
    body['declareStatements'] = declare_statements
    body['type'] = tType
    url = os.path.join(PROSEBASEURL, 'transformations', 'learntransformation')
    response = requests.post(url, json=body)
    if response.status_code != 200:
        abort(response.status_code)

    print("response from prose:", response);
    print("response from prose:", json.dumps(response.json()))

    #save to database
    cur = None
    for possible_t in response.json():
        hash_val = hashlib.sha256(possible_t["humanReadableAst"].encode('utf-8')).hexdigest()
        cur = get_db().execute('REPLACE INTO learned_programs(hash, human_readable_ast, xml_ast, comment) VALUES (?,?,?, ?)',(hash_val,
                                                                                                                             possible_t["humanReadableAst"],
                                                                                                                             possible_t["xmlAst"],
                                                                                                                             ""))
    if cur is not None:
        get_db().commit()
        cur.close()

    return json.dumps({'status': "success", "response": response.json()})
    
def apply_transformation():
    request_params = request.get_json()
    exp_name = request_params.get('expName', '')
    chosen_program = request_params.get('selectedProgram', '')
    exp_folder = os.path.join(MEDIA, exp_name)
    spacer_instance = get_spacer_instance(exp_name)
    declare_statements = get_declare_statements(exp_folder)
    print(json.dumps(spacer_instance, indent=4)[:200])
    body = {
        'declareStatements': declare_statements,
        'program': chosen_program,
        'spacerInstance': json.dumps(spacer_instance)
    }
    url = os.path.join(PROSEBASEURL, 'transformations', 'applytransformation')
    response = requests.post(url, json=body)
    if response.status_code != 200:
        abort(response.status_code)

    return json.dumps({'status': "success", "response": response.json()})

def apply_multi_transformation():
    """
    This endpoint allows us to apply multiple transformation on top of eachother
    It is essentially the same as apply_transformation, but use the expr_map sent by
    the frontend, instead of from the db, a.k.a line

    spacer_instance = {"Id": exp_name, "Lemmas": lemmas}
    vs
    spacer_instance = get_spacer_instance(exp_name)
    """
    request_params = request.get_json()
    exp_name = request_params.get('expName', '')
    lemmas = request_params.get('lemmas', {})
    chosen_program = request_params.get('selectedProgram', '')
    exp_folder = os.path.join(MEDIA, exp_name)
    spacer_instance = {"Id": exp_name, "Lemmas": lemmas}
    declare_statements = get_declare_statements(exp_folder)
    print(json.dumps(spacer_instance, indent=4)[:200])
    body = {
        'declareStatements': declare_statements,
        'program': chosen_program,
        'spacerInstance': json.dumps(spacer_instance)
    }
    url = os.path.join(PROSEBASEURL, 'transformations', 'applytransformation')
    response = requests.post(url, json=body)
    if response.status_code != 200:
        abort(response.status_code)

    return json.dumps({'status': "success", "response": response.json()})

def get_declare_statements(exp_folder):
    temp_result = []
    with open(os.path.join(exp_folder, "var_decls"), "r") as f:
        for line in f:
            temp_result.append(line.strip())

    return "\n".join(temp_result)

def save_exprs(dynamodb=None):
    status = "success"
    try:
        request_params = request.get_json()
        exp_name = request_params.get('expName', '')
        expr_map = request_params.get('expr_map', '')
        expr_map = json.loads(expr_map)
        exp_folder = os.path.join(MEDIA, exp_name)

        cur = None
        for k in expr_map:
            #use replace to insert
            cur = get_db().execute('REPLACE INTO expr_map(exp_name, expr_id, value) VALUES (?,?,?)',(exp_name,
                                                                                                     int(k),
                                                                                                     json.dumps(expr_map[k])))
        if cur is not None:
            get_db().commit()
            cur.close()

    except Exception as e:
        traceback.print_exc()
        status = "Error: {}".format(e)
    return json.dumps({'status': status})

def get_exprs(): 
    request_params = request.get_json()
    exp_name = request_params.get('expName', '')


    print("exp_name", exp_name)
    expr_map = get_expr_map(exp_name)

    return json.dumps({'status': "success",
                       'expr_map': expr_map})

def start_spacer():
    request_params = request.get_json()
    file_content = request_params.get('file', '')
    exp_name = request_params.get('expName', '')
    new_exp_name = get_new_exp_name(exp_name)
    print(new_exp_name)
    insert_db('INSERT INTO exp(exp_name, done, result, aux, time) VALUES (?,?,?,?,?)',(new_exp_name, 0, "UNK", "NA", 0))

    spacer_user_options = request_params.get("spacerUserOptions", "")
    var_names = request_params.get("varNames", "")
    print("var_names", var_names)
    exp_folder = os.path.join(MEDIA, new_exp_name)
    os.mkdir(exp_folder)

    input_file = open(os.path.join(exp_folder, "input_file.smt2"), "wb")
    input_file.write(str.encode(file_content))
    input_file.flush() # commit file buffer to disk so that Spacer can access it

    stderr_file = open(os.path.join(exp_folder, "stderr"), "w")
    stdout_file = open(os.path.join(exp_folder, "stdout"), "w")

    run_args = [args.z3_path]
    run_args.extend(spacer_user_options.split())
    run_args.extend(options_for_visualization)
    run_args.append(os.path.abspath(os.path.join(exp_folder, 'input_file.smt2')))
    print(run_args)

    with open(os.path.join(exp_folder, "run_cmd"), "w") as f:
        run_cmd = " ".join(run_args)
        f.write(run_cmd)

    #save VarNames
    with open(os.path.join(exp_folder, "var_names"), "w") as f:
        f.write(var_names)
        
    Popen(run_args, stdin=PIPE, stdout=stdout_file, stderr=stderr_file, cwd = exp_folder)

    return json.dumps({'status': "success", 'spacer_state': "running", 'exp_name': new_exp_name})

def upload_files():
    def _write_file(exp_folder, content, name):
        #write file to the exp_folder
        _file = open(os.path.join(exp_folder, name), "wb")
        _file.write(str.encode(content))
        _file.flush() # commit file buffer to disk so that Spacer can access it



    request_params = request.get_json()
    spacer_log = request_params.get('spacerLog', '')
    input_file = request_params.get('inputProblem', '')
    spacer_state = request_params.get('spacerState', 'uploaded')
    run_cmd = request_params.get('runCmd', '')
    exp_name = request_params.get('expName', '')
    new_exp_name = get_new_exp_name(exp_name)
    insert_db('INSERT INTO exp(exp_name, done, result, aux, time) VALUES (?,?,?,?,?)',(new_exp_name, False, "UNK", "NA", 0))
    exp_folder = os.path.join(MEDIA, new_exp_name)
    os.mkdir(exp_folder)

    #write input file
    _write_file(exp_folder, input_file, "input_file.smt2")
    _write_file(exp_folder, spacer_log, "spacer.log")
    _write_file(exp_folder, run_cmd, "run_cmd")
    _write_file(exp_folder, spacer_state, "stdout")

    return json.dumps({'status': "success", 'message': "success"})

def poke():
    #TODO: finish parsing using all the files in the exp_folder (input_file, etc.)
    request_params = request.get_json()
    exp_name = request_params.get('expName', '')

    #check if it is already in the db
    in_db = query_db("SELECT * FROM nodes_list WHERE exp_name = ?", (exp_name,))

    if in_db:
        assert(len(in_db) == 1)
        res = json.loads(in_db[0]['nodes_list'])
    else:
        res = ms.parse_exp(exp_name)


    return json.dumps(res)



@app.route('/spacer/fetch_exps', methods=['POST'])
def handle_fetch_exps():
    return pooling()
@app.route('/spacer/fetch_progs', methods=['POST'])
def handle_fetch_progs():
    return fetch_progs()
@app.route('/spacer/fetch_options', methods=['POST'])
def handle_fetch_options():
    return fetch_options()
@app.route('/spacer/start_iterative', methods=['POST'])
def handle_start_spacer_iterative():
    return start_spacer()
@app.route('/spacer/poke', methods=['POST'])
def handle_poke():
    return poke()
@app.route('/spacer/save_exprs', methods=['POST'])
def handle_save():
    return save_exprs()
@app.route('/spacer/get_exprs', methods=['POST'])
def handle_get():
    return get_exprs()
@app.route('/spacer/learn_transformation', methods=['POST'])
def handle_learn_transform():
    return learn_transformation()
@app.route('/spacer/apply_transformation', methods=['POST'])
def handle_apply_transform():
    return apply_transformation()
@app.route('/spacer/apply_multi_transformation', methods=['POST'])
def handle_apply_multi_transform():
    return apply_multi_transformation()
@app.route('/spacer/upload_files', methods=['POST'])
def handle_upload_files():
    return upload_files()
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
