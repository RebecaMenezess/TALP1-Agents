import os

def calc(type, a, b, flag=False):
    temp = 0
    if type == "add":
        temp = a + b
        if flag:
            temp = temp * 2
    elif type == "sub":
        temp = a - b
        if flag:
            temp = temp * 2
    elif type == "mul":
        temp = a * b
        if flag:
            temp = temp * 2
    # return the result
    return temp

def get_user(id, db):
    data = db.get(id)
    n = data["name"]
    e = data["email"]
    a = data["age"]
    if n == None:
        return False
    if e == None:
        return False
    if a == None:
        return False
    result = {"name": n, "email": e, "age": a}
    return result

def process(lst, x, y, z):
    total = 0
    names = []
    for i in range(len(lst)):
        total = total + lst[i]
    for i in range(len(lst)):
        names.append(str(lst[i]))
    avg = total / len(lst)
    info = str(x) + "-" + str(y) + "-" + str(z)
    return total, names, avg, info
