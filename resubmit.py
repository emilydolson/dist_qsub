import glob, os, re, sys, shutil
from optparse import OptionParser
# This script searches the current working directory for runs that did not
# get to the number of updates specified by the first command-line argument
# and creates a new run_list file to resubmit all of them. If any runs ended
# early due to natural causes (i.e. the population went to 0), they are not
# resubmitted and are instead recorded in the "extinct" file.


def _build_header(rl_file):
    """
    Given a run_list file, grab and return the header.
    """
    header = ""
    with open(rl_file, "r") as fp:
        for line in fp:
            if line == "\n":
                break
            header += line
    return header


parser = OptionParser()

parser.add_option("-u", "--updates", action="store", dest="updates", default="100000", type="string", help="The number of updates each run should have gone for (default: 100000)")
parser.add_option("-g", "--generations", action="store", dest="generations", default="", type="string", help="Base completion off of generations, and set expected number of generations each run should have gone for")
parser.add_option("-r", "--reps", action="store", dest="reps", default=10, type="int", help="The number of random seeds runs per condition (default: 10)")
parser.add_option("-c", "--checkpoint", action="store_true", dest="cpr", default=False, help="Restart from checkpoint? WARNING: Only resubmits runs with valid checkpoint")
parser.add_option("-n", "--nocheckpoint", action="store_true", dest="nocpr", default=False, help="Only include runs without a checkpoint - i.e. those missed by running this with the -c flag")
parser.add_option("-i", "--infer-missing", action="store_true", dest="infer", default=False, help="Use specified number of reps to find probably missing runs. Experimental.")
parser.add_option("-t", "--compare-to-run-list", action="store_true", dest="comp_to_rl", default=False, help="If set, test to see if all conditions in the provided run_list that aren't commented out are accounted for.")
parser.add_option("-l", "--run_list", action="store", dest="rl_file", default="", help="If set, use the provided run list file to build header.")

(options, args) = parser.parse_args()

run_list = open("run_list_resubmit", "wb")
extinct = open("extinct", "wb")

default_header = "set description avida_experiment\nset email default@msu.edu\nset email_when final\nset walltime 4\nset mem_request 4\nset config_dir configs\nset dest_dir " + os.getcwd() + "\n"
header = None
if options.rl_file != "":
    try:
        header = _build_header(options.rl_file)
    except:
        print("Could not build header from provided run_list file. Using default.")
        header = default_header

if not header:
    header = default_header

if options.cpr == 1:
    header += "set cpr 1\n"

header += "\n"

run_list.write(header)

conditions = {}

if options.rl_file != "":
    dest_dir = header.partition("dest_dir ")[-1].strip()
    if dest_dir == "":
        dest_dir = "."
    else:
        dest_dir = dest_dir.split("\n")[0]
        if dest_dir[0] != "/" and os.getcwd().split("/")[-1] == dest_dir.strip("/").split("/")[-1]:
            dest_dir = "."
    print("Using", dest_dir, "as dest_dir")
    run_logs = glob.glob(dest_dir+"/*/run.log")
else:
    run_logs = glob.glob("./*/run.log")

if run_logs == []:
    print("Warning: No files found. Are you running this from dest_dir or its parent directory?")

extinct_list = []
not_resubmitted = []

for run in run_logs:
    if "_bak" in run:
        continue

    with open(run) as logfile:

        end = logfile.readlines()[-1].split()
        if len(end) < 6 or end[0] != "UD:":
            print(end)
            pop = 1 #all that matters is it's not 0
            ud = 0
            gen = 0
        else:
            pop = end[-1]
            ud = end[1]
            gen = end[3]

        rep = run.split("/")[-2]
        split_condition = rep.split("_")
        seed = split_condition[-1]
        condition = "_".join(split_condition[:-1])
        condition = condition.strip("./ ")

        if condition in conditions:
            conditions[condition]["found_seeds"].append(int(seed))
        else:
            conditions[condition] = {}
            conditions[condition]["seeds"] = []
            conditions[condition]["found_seeds"] = [int(seed)]
            conditions[condition]["name"] = condition

        if "command" not in conditions[condition]:
            if os.path.exists(rep+"/command.sh"):
                command_file = open(rep+"/command.sh")
                command = command_file.readlines()[1]
                split_command = command.split()
                seed_ind = split_command.index("-s")
                split_command[seed_ind+1] = "$seed"
                command = " ".join(split_command[:-5]) # -5 to remove piping to run.log
                command_file.close()

                conditions[condition]["command"] = command


        if (options.generations == "" and ud != options.updates) or (options.generations != "" and float(gen) < float(options.generations)):
            if pop == "0":
                extinct_list.append(rep)
                continue

            if os.path.exists(rep+"/checkpoint_safe.blcr") and options.cpr:
                try:
                    shutil.copy(rep+"/checkpoint_safe.blcr", rep+"/checkpoint.blcr")
                except IOError as e:
                    '''Note: Technically we should check if e.errno==EACCES
                    or switch to py3 to use PermissionError'''
                    print("Not resubmitting", rep, "because don't have permission. ", e)
                    not_resubmitted.append(rep)
                    continue

            elif options.cpr:
                print("Not resubmitting", rep, "because there's no checkpoint.")
                not_resubmitted.append(rep)
                continue
            elif os.path.exists(rep+"/checkpoint_safe.blcr") and options.nocpr:
                print("Not resubmitting", rep, "because there's a checkpoint.")
                not_resubmitted.append(rep)
                continue

            print("resubmit: ", rep)
            conditions[condition]["seeds"].append(int(seed))


for condition in conditions:

    found_seeds = conditions[condition]["found_seeds"]
    seeds = conditions[condition]["seeds"]
    name = conditions[condition]["name"]
    command = "COMMAND NOT FOUND - PLEASE FIX BEFORE RESUBMITTING"
    if "command" in conditions[condition]:
        command = conditions[condition]["command"]
    elif options.rl_file != "":
        with open(options.rl_file) as fp:
            for line in fp:
                if len(line.split()) < 2:
                    continue
                if line.split()[1] == name:
                    command = " ".join(line.split()[2:])

    if options.infer and len(found_seeds) < options.reps:
        found_seeds.sort()
        print(len(found_seeds), options.reps, found_seeds)

        all_seeds = range(found_seeds[0], found_seeds[-1]+1)

        if len(all_seeds) < options.reps:

            if options.rl_file != "":
                print("Inferring", name, "seed from run_list")
                with open(options.rl_file) as fp:
                    for line in fp:
                        if len(line.strip()) < 2:
                            continue
                        if line.strip().split()[1] == name:
                            seeds = line.strip().split()[0]
                            seeds = seeds.split("..")
                all_seeds = range(int(seeds[0]), int(seeds[1]))

            else:

                #Ewww, we have to do this the hard way
                print("Warning: Speculative inference for", condition)
                best = max(conditions.values(), key=lambda x: len(x["found_seeds"]))
                best = best["found_seeds"]
                if len(best) < options.reps:
                    #Well this isn't going to work
                    print("Inference failed for", condition, " - no conditions have the right number of directories")
                else:
                    best.sort()
                    if min(best) > all_seeds[-1]:
                        curr = min(best)
                        while curr > all_seeds[-1]:
                            curr -= options.reps
                        all_seeds = range(curr, curr+options.reps)
                    else:
                        curr = max(best)
                        while curr < all_seeds[0]:
                            curr += options.reps
                        all_seeds = range(curr-options.reps+1, curr+1)

        add_seeds = set(all_seeds) - set(found_seeds)
        print("Inferred missing seeds:", condition, add_seeds)

        seeds += add_seeds

    elif len(found_seeds) != options.reps:
        print("Warning! Wrong number of reps found for", condition, "Expected:", options.reps, "Found:", len(found_seeds))



    seeds.sort()
    first = 0
    second = 0
    while second < len(seeds) and first < len(seeds):
        second = first
        while second < len(seeds) - 1 and int(seeds[second])+1 == int(seeds[second+1]):
            second += 1

        #We have isolated a chunk of numbers

        if second == first:
            run_list.write(str(seeds[first]) + " " + name + " " + command + "\n")
        else:
            run_list.write(str(seeds[first])+".."+str(seeds[second]) + " " + name + " " + command + "\n")

        first = second + 1

    if options.rl_file != "" and options.comp_to_rl:
        with open(options.rl_file) as fp:
            for line in fp:
                sline = line.strip()
                if sline == "":
                    continue
                sline = sline.split()
                if sline[0] == "set":
                    continue
                if sline[0] != "" and sline[0][0] == "#":
                    continue

                # Okay, that should have filtered out everything that isn't
                # an experiment specification
                if len(sline) > 1 and sline[1] not in conditions:
                    print(sline[1], "in run_list but no results directories found. Adding to resubmit list")
                    run_list.write(line)
    elif options.rl_file == "" and options.comp_to_rl:
        print("Warning: Comparison to run_list requested but no run_list provided. Use the -l flag to provide one")

extinct.write("\n".join(extinct_list))
