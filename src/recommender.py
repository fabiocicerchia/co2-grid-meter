
def recommend(ci):
    if ci < 200:
        return "RUN NOW"
    if ci < 350:
        return "OK"
    return "WAIT"
