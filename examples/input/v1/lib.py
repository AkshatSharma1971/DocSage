MAX_SIZE = 100


def fetch(url, timeout=10, retries=3):
    return _clean(url)


def upload(path, chunk=1024):
    return path


def legacy_login(user):
    return user


def _clean(x):
    return x
