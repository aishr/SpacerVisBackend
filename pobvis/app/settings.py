import os
if os.environ.get('BACKEND_DATA_PATH') is not None:
    BACKEND_DATA_PATH = os.environ['BACKEND_DATA_PATH']
    DATABASE = os.path.join(BACKEND_DATA_PATH, 'exp_db')
    MEDIA = os.path.join(BACKEND_DATA_PATH, 'media')
else:
    BACKEND_DATA_PATH = None
    DATABASE = './exp_db'
    MEDIA = './media'

PROSEBASEURL = 'http://SpacerProseBackend:2000/api/v1/'

print('DATABASE=', os.path.abspath(DATABASE))
print('MEDIA=', os.path.abspath(MEDIA))

options_for_visualization = ["fp.spacer.trace_file=spacer.log", "fp.print_statistics=true", "-v:1"]
