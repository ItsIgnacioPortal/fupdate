process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)

while process.stdout.readable():
    line = process.stdout.readline()
    if not line:
        break
    print(str(line.strip())[1:])