from flask import g
import pysmt.operators as pyopt
import sqlite3
from settings import DATABASE, MEDIA, options_for_visualization
import json
from datetime import datetime
import psutil

def safe_read(file_path):
    try:
        with open(file_path, "r") as f:
            data = f.readlines()
            if len(data)==0:
                return [""]
            else:
                return data
    except Exception as e:
        print(e)
        return [""]

def get_expr_map(exp_name):
    expr_map = {}
    expr_from_exp_name = query_db('SELECT * FROM expr_map WHERE exp_name=?',(exp_name,))
    for r in expr_from_exp_name:
        expr_id = r['expr_id']
        value = json.loads(r['value'])
        expr_map[expr_id] = value

    return expr_map

def get_spacer_instance(exp_name):
    return {"Id": exp_name, "Lemmas": get_expr_map(exp_name)}

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv
def insert_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    get_db().commit()
    cur.close()

def fetch_exps():
    exps_list = []
    for exp in query_db('select * from exp'):
        r = {}
        for k in exp.keys():
            r[k] = exp[k]
        exps_list.append(r)
    return json.dumps({'status': "success", 'exps_list':exps_list})

def fetch_progs():
    # request_params = request.get_json()
    # exp_name = request_params.get('exp_name', '')
    progs_list = []
    for prog in query_db('select * from learned_programs'):
        r = {}
        for k in prog.keys():
            r[k] = prog[k]
        progs_list.append(r)
    return json.dumps({'status': "success", 'progs_list':progs_list})


def get_new_exp_name(exp_name):
    now = datetime.now()
    current_time = now.strftime("%d%m%y_%H_%M_%S")
    return exp_name+"_"+current_time

def calculate_val(node):
    if node.is_real_constant():
        frac = node._content.payload
        val = frac.numerator / frac.denominator
        return round(val, 4)
    return str(node._content.payload[0])

def to_json(node, debug = False):
    if debug: print(node, node.get_type(), node.args())
    if node.is_real_constant():
        type_str = "0_REAL_CONSTANT" #hack to put real constant at the end
    else:

        type_str = pyopt.op_to_str(node.node_type())
        if debug:
            print("NODE TYPE:", node.node_type())
            print("TYPE_STR:", type_str)
    if len(node.args())==0:
        obj = {"type": type_str, "content":calculate_val(node)}
        return obj
    else:
        args = []
        for a in node.args():
            args.append(to_json(a, debug))
        obj = {"type": type_str, "content": args}
        return obj

def order_node(node):
    args = node["content"]
    if isinstance(args, list):
        for idx in range(len(args)):
            args[idx] = order_node(args[idx])
        #only order commutative operators
        if node["type"]=="PLUS" or node["type"]=="TIMES" or node["type"]=="AND":
            args = sorted(args, key=lambda k: (k["type"], str(k["content"])), reverse = True) 
        node["content"] = args
    return node

def check_if_process_running(processName):
    '''
    Check if there is any running process that contains the given name processName.
    '''
    #Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            # Check if process name contains the given name string.
            cmdline = " ".join(proc.cmdline())
            if 'z3' in cmdline:
                print(cmdline)
            if processName in cmdline:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False;

def get_spacer_state(stderr, stdout):
    """
    must return one of the state in accepted states
    """
    accepted_states = ["sat", "unsat", "unknown", "running", "uploaded"]
    res = "running"
    #TODO: implement me
    if stdout[0] != '':
        res = stdout[0].strip()

    print(res)
    assert(res in accepted_states)
    return res
