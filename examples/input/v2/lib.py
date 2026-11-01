MAX_SIZE = 500


def fetch(url, timeout=30, attempts=3):
    return _clean(url).strip()


def upload(path, chunk=2048):
    return path


def _clean(x):
    return x.strip()
