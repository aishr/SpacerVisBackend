#!/bin/sh
rm exp_db
rm -rf media
mkdir media
sqlite3 exp_db "create table exp(name varchar(100), done bool, result varchar(5), time int, aux varchar(200));"
sqlite3 exp_db "create table expr_map(exp_path varchar(100), expr_id int, value text, PRIMARY KEY ( exp_path, expr_id));"
sqlite3 exp_db "create table learned_programs(hash varchar(256), human_readable_ast text, xml_ast text, comment text, PRIMARY KEY(hash));"
