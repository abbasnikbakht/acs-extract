#!/usr/bin/env python

# Extract data from the ACS summary file
# Only tested on 2016 Summary File estimates

from argparse import ArgumentParser
from os.path import dirname, join
from sys import argv
from csv import DictReader, reader, DictWriter
from collections import defaultdict
import codecs

parser = ArgumentParser(description='Reformat an ACS summary file into a meaningful CSV')
parser.add_argument('--index', default=join(dirname(argv[0]), 'lookup_tables', '2016_5yr.csv'),
    help='Path to the lookup table ( CSV format) for the summary file you\'re using; defaults to the index for 2016 5-year estimates')
parser.add_argument('--blockgroups', action='store_true', default=False, help='Extract data for Census block groups')
parser.add_argument('--tracts', action='store_true', default=False, help='Extract data for Census tracts')
parser.add_argument('--long-titles', action='store_true', default=False, help='Use long titles in CSV output')
parser.add_argument('path', metavar='PATH_TO_ACS_SUMMARY_FILE', help='Path to an unzipped ACS summary file')
parser.add_argument('vars', metavar='VAR', nargs='+', help='Variables to extract, in format TABLE_VARIABLENUMBER, TABLE_START-END, or TABLE_*')
parser.add_argument('output', metavar='OUTPUT_CSV', help='Output CSV file')
args = parser.parse_args()

print(args)

# Parse the tables/variables wanted
class Variable(object):
    def __init__(self, table, number, offset, sequence, name):
        self.table = table
        self.number = number
        self.offset = offset
        self.sequence = sequence
        self.name = name

variablesBySequence = defaultdict(list)

tables = defaultdict(list)
for var in args.vars:
    table, var = var.split('_')
    tables[table].append(var)

# Read the geography file
geoids = dict()
# TODO HARDWIRED PATH
with open(join(args.path, 'g20165ca.txt'), 'rb') as g: # Because hey, we couldn't be standard and use valid Unicode
    for line in g:
        # fixed width files are THE WORST. Punchcards have been obsolete for 30 years, let's stop using formats inspired
        # by them, huh?
        geoid = (line[25:30] + line[40:47]).decode('ascii').rstrip()
        if line[46:47].decode('ascii') != ' ':
            typ = 'blockgroup'
        elif line[40:46].decode('ascii').strip() != '':
            typ = 'tract'
        else:
            continue

        logrecno = line[13:20].decode('ascii')
        geoids[logrecno] = dict(geoid=geoid, type=typ)

# Read the index
with open(args.index) as index:
    rdr = DictReader(index)

    tableOffset = 0
    currentTableId = None
    readAll = False
    # Variables to read, these are 1-based
    toRead = set()
    baseTitle = ''
    for line in rdr:
        if not line['Table ID'] in tables:
            continue

        if not line['Table ID'] == currentTableId:
            # New table, reset per-table stuff
            readAll = False
            toRead = set()
            currentTableId = line['Table ID']
            tableOffset = int(line['Start Position']) - 1 # Correct for off-by-one
            baseTitle = ''
            # Parse the variable specs
            for spec in tables[currentTableId]:
                if spec == '*':
                    readAll = True
                elif '-' in spec:
                    start, end = map(int, spec.split('-'))
                    for i in range(start, end + 1):
                        toRead.add(i)
                else:
                    toRead.add(int(spec))
            print(f'reading {"all " if readAll else ""}vars {toRead if not readAll else ""} from table {currentTableId}')
        else:
            # continue reading existing table
            if line['Line Number'] == '':
                continue # Universe Line

            lineNumber = int(line['Line Number'])
            sequenceNumber = int(line['Sequence Number'])

            # We do all this so hierarchical titles are correct even if the top level variable is not selected
            if line['Table Title'].endswith(':'):
                title = line['Table Title'][:-1]
                baseTitle = line['Table Title'] + ' '
            else:
                title = baseTitle + line['Table Title']

            offset = tableOffset + lineNumber - 1 # convert to 0 based

            if readAll or lineNumber in toRead:
                var = Variable(table=currentTableId, number=lineNumber, sequence=sequenceNumber, offset=offset, name=title)
                variablesBySequence[sequenceNumber].append(var)

print('Reading the following variables: ')
varsToRead = [i for seq in variablesBySequence.values() for i in seq]
varsToRead.sort(key=lambda x: f'{x.table}_{x.number:03d})')
for var in varsToRead:
    print(f'{var.table}_{var.number:03d}: {var.name}')

rows = defaultdict(dict) # geoid to row values

colnames = set(['geoid'])

for sequence, variables in variablesBySequence.items():
    # First read estimates
    # TODO hardwired path
    for prefix in ('e', 'm'):
        with open(join(args.path, f'{prefix}20165ca{sequence:04d}000.txt'), 'r') as inp:
            rdr = reader(inp)

            for line in rdr:
                # find geoid
                geoid = geoids[line[5]]
                if args.blockgroups and geoid['type'] == 'blockgroup' or args.tracts and geoid['type'] == 'tract':
                    row = rows[geoid['geoid']]
                    row['geoid'] = geoid['geoid']
                    for var in variables:
                        if args.long_titles:
                            if prefix == 'e':
                                col = var.name
                            else:
                                col = 'Margin of Error on ' + var.name
                        else:
                            if prefix == 'e':
                                col = f'{var.table}_{var.number:03d}'
                            else:
                                col = f'{var.table}_{var.number:03d}_MOE'

                        colnames.add(col)
                        row[col] = line[var.offset]

with open(args.output, 'w') as out:
    colnames = list(colnames)
    colnames.sort()
    writer = DictWriter(out, fieldnames=colnames)
    writer.writeheader()
    writer.writerows(rows.values())