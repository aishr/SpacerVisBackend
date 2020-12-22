"""Style guide: use underscore for all variable and function names"""
import requests
import boto3
import sys
if sys.version_info.major < 3:
    raise Exception("User error: This application only supports Python 3, so please use python3 instead of python!")
import json
from flask import Flask, request, abort
from flask_cors import CORS
import tempfile
import argparse
from chctools import horndb as H
import io
import os
from os import environ
from settings import DATABASE, MEDIA, PROSEBASEURL, options_for_visualization
from subprocess import PIPE, STDOUT, Popen, run
from chctools import horndb as H
from utils.utils import *
import utils.trace_parsing as ms
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
        exps_list.append(exp["name"])

    for exp in exps_list:
        print("EXP:", exp)
        is_running = check_if_process_running(exp)
        if not is_running:
            get_db().execute('UPDATE exp SET done = 1 WHERE name = ?', (exp,));

    #commit
    get_db().commit()

def pooling():
    update_status()
    return fetch_exps()

def learn_transformation():
    request_params = request.get_json()
    exp_path = request_params.get('exp_path', '')
    exp_folder = os.path.join(MEDIA, exp_path)
    declare_statements = get_declare_statements(exp_folder)
    body = {
        'instance': exp_path,
        'declareStatements': declare_statements
    }
    url = os.path.join(PROSEBASEURL, 'learntransformation')
    response = requests.post(url, json=body)
    if response.status_code != 200:
        abort(response.status_code)

    with open(os.path.join(exp_folder, "possible_transformations"), "w") as f:
         f.write(json.dumps(response.json()))
    return json.dumps({'status': "success", "response": response.json()})

def learn_transformation_modified():
    request_params = request.get_json()
    exp_path = request_params.get('exp_path', '')
    exp_folder = os.path.join(MEDIA, exp_path)
    inputOutputExamples = request_params.get('inputOutputExamples', '')
    params = request_params.get('params', '')
    tType = request_params.get('type', '')
    body = {
        'instance': exp_path,
        'inputOutputExamples': inputOutputExamples
    }
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
    url = os.path.join(PROSEBASEURL, 'transformations', 'learntransformationmodified')
    response = requests.post(url, json=body)
    if response.status_code != 200:
        abort(response.status_code)

    with open(os.path.join(exp_folder, "possible_transformations"), "w") as f:
         f.write(json.dumps(response.json()))
    return json.dumps({'status': "success", "response": response.json()})
    
def apply_transformation():

    request_params = request.get_json()
    exp_path = request_params.get('exp_path', '')
    chosen_program = request_params.get('selectedProgram', '')
    exp_folder = os.path.join(MEDIA, exp_path)
    declare_statements = get_declare_statements(exp_folder)
    body = {
        'instance': exp_path,
        'declareStatements': declare_statements,
        'program': chosen_program
    }
    url = os.path.join(PROSEBASEURL, 'transformations', 'applytransformation')
    response = requests.post(url, json=body)
    if response.status_code != 200:
        abort(response.status_code)

    with open(os.path.join(exp_folder, "transformed_expr_map"), "w") as f:
         f.write(json.dumps(response.json()))
    return json.dumps({'status': "success", "response": response.json()})

def get_declare_statements(exp_folder):
    temp_result = []
    with open(os.path.join(exp_folder, "var_decls"), "r") as f:
        for line in f:
            temp_result.append(line.strip())

    return "\n".join(temp_result)

def save_exprs(dynamodb=None):
    region = environ.get('REGION_NAME')
    access_key = environ.get('ACCESS_KEY_ID')
    secret_key = environ.get('SECRET_ACCESS_KEY')
    table_name = environ.get('TABLE_NAME')
    if not dynamodb:
        dynamodb = boto3.resource(
                'dynamodb',
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key
        )
        client = boto3.client(
                'dynamodb',
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key
        )
    existing_tables = client.list_tables()['TableNames']
    if table_name not in existing_tables:
        table = dynamodb.create_table(
            TableName=table_name,
            AttributeDefinitions=[
                {'AttributeName': 'Id', 'AttributeType': 'S'},
            ],
            KeySchema=[
                {'AttributeName': 'Id', 'KeyType': 'HASH'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5,
            }
        )
        
    else:
        table = dynamodb.Table(table_name)

    table_info = client.describe_table(
        TableName=table_name
    )
    table_status = table_info['Table']['TableStatus']
    while table_status != "ACTIVE":
        table_info = client.describe_table(
            TableName=table_name
        )
        table_status = table_info['Table']['TableStatus']
    request_params = request.get_json()
    exp_path = request_params.get('exp_path', '')
    expr_map = request_params.get('expr_map', '')
    exp_folder = os.path.join(MEDIA, exp_path)

    with open(os.path.join(exp_folder, "expr_map"), "w") as f:
        f.write(expr_map)

    dbData = json.loads(expr_map)
    dbData["Id"] = exp_path
    response = table.put_item(Item=dbData)

    return json.dumps({'status': "success" if response['ResponseMetadata']['HTTPStatusCode'] == 200 else "error"})

def get_exprs(): 
    request_params = request.get_json()
    exp_path = request_params.get('exp_path', '')
    exp_folder = os.path.join(MEDIA, exp_path)

    expr_map = safe_read(os.path.join(exp_folder, "expr_map"))
    return json.dumps({'status': "success",
                       'expr_map': expr_map[0]})

def start_spacer():
    request_params = request.get_json()
    file_content = request_params.get('file', '')
    exp_name = request_params.get('name', '')
    new_exp_name = get_new_exp_name(exp_name)
    print(new_exp_name)
    insert_db('INSERT INTO exp(name, done, result, aux, time) VALUES (?,?,?,?,?)',(new_exp_name, 0, "UNK", "NA", 0))

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
    input_file = request_params.get('inputFile', '')
    run_cmd = request_params.get('runCmd', '')
    new_exp_name = request_params.get('expName', '')
    insert_db('INSERT INTO exp(name, done, result, aux, time) VALUES (?,?,?,?,?)',(new_exp_name, 0, "UNK", "NA", 0))
    exp_folder = os.path.join(MEDIA, new_exp_name)
    os.mkdir(exp_folder)

    #write input file
    _write_file(exp_folder, input_file, "input_file.smt2")
    _write_file(exp_folder, spacer_log, "spacer.log")
    _write_file(exp_folder, run_cmd, "run_cmd")

    return json.dumps({'status': "success", 'message': "success"})

def save_var_rels(rel, f):
    if (rel.name() == "simple!!query"):
        return
    file_line = "(declare-const {name} ({sort}))\n"
    for i in range(rel._fdecl.arity()):
        name = rel._mk_arg_name(i)
        sort = str(rel._fdecl.domain(i)).replace(",", "").replace("(", " ").replace(")", "")
        f.write(file_line.format(name=name, sort=sort))

def poke():
    #TODO: finish parsing using all the files in the exp_folder (input_file, etc.)
    request_params = request.get_json()
    exp_path = request_params.get('exp_path', '')
    exp_folder = os.path.join(MEDIA, exp_path)
    nodes_list = []
    run_cmd = ""
    stdout = safe_read(os.path.join(exp_folder, "stdout"))
    stderr = safe_read(os.path.join(exp_folder, "stderr"))
    z3_trace = safe_read(os.path.join(exp_folder, ".z3-trace"))
    spacer_log = safe_read(os.path.join(exp_folder, "spacer.log"))
    run_cmd = safe_read(os.path.join(exp_folder, "run_cmd"))[0].strip()
    temp_var_names = safe_read(os.path.join(exp_folder, "var_names")) 
    var_names = temp_var_names[0].strip() if temp_var_names != [] else ""
    expr_map = safe_read(os.path.join(exp_folder, "expr_map"))

    status = "success"
    spacer_state = get_spacer_state(stderr, stdout)
    #load the file into db for parsing
    try:
        db = H.load_horn_db_from_file(os.path.join(exp_folder, "input_file.smt2"))
        rels = []
        for rel_name in db._rels:
            rel = db.get_rel(rel_name)
            rels.append(rel)
        with open(os.path.join(exp_folder, "var_decls"), "w") as f:
            for rel in rels:
                save_var_rels(rel, f);
    except:
        status = "error in loading horndb. skip parsing the file"

    #TODO: only read spacer.log when there are no errors
    nodes_list = ms.parse(spacer_log)
    #parse expr to json
    for idx in nodes_list:
        node = nodes_list[idx]
        if node["exprID"]>2:
            expr = node["expr"]
            expr_stream = io.StringIO(expr)
            try:
                ast = rels[0].pysmt_parse_lemma(expr_stream)
                ast_json = order_node(to_json(ast))
                node["ast_json"] = ast_json

            except Exception as e:
                # PySMT has a bug in __str__ of the Exception, hence for now we need to turn off the debug message here
                # print("expr stream:", expr)
                # print("Exception when ordering the node:", e)
                # print("Broken Node", node)
                # print("Broken Node exprID:", node["exprID"])
                node["ast_json"] = {"type": "ERROR", "content": "trace is incomplete"}


    return json.dumps({'status': "success",
                       'spacer_state': spacer_state,
                       'nodes_list': nodes_list,
                       'run_cmd': run_cmd,
                       'var_names': var_names,
                       'expr_map': expr_map[0]})


@app.route('/spacer/fetch_exps', methods=['POST'])
def handle_fetch_exps():
    return pooling()
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
@app.route('/spacer/learn_transformation_modified', methods=['POST'])
def handle_learn_transform_modified():
    return learn_transformation_modified()
@app.route('/spacer/apply_transformation', methods=['POST'])
def handle_apply_transform():
    return apply_transformation()
@app.route('/spacer/upload_files', methods=['POST'])
def handle_upload_files():
    return upload_files()
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
