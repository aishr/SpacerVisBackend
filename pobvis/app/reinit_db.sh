#!/bin/sh
rm exp_db
rm -rf media
mkdir media
sqlite3 exp_db "CREATE TABLE exp(exp_name VARCHAR(100), done BOOL, result VARCHAR(5), time INT, aux VARCHAR(200));"
sqlite3 exp_db "CREATE TABLE expr_map(exp_name VARCHAR(100), expr_id INT, value TEXT, PRIMARY KEY ( exp_name, expr_id));"

# schema for nodes_list:
# not used yet. nodes_list could be very big. Need to make sure it is not too big
sqlite3 exp_db "CREATE TABLE nodes_list(exp_name VARCHAR(100), nodes_list TEXT, PRIMARY KEY (exp_name));"
sqlite3 exp_db "CREATE TABLE learned_programs(hash VARCHAR(256), human_readable_ast TEXT, xml_ast TEXT, comment TEXT, PRIMARY KEY(hash));"
