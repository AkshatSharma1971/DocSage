# Demo Library

## `fetch()`

The `timeout` parameter defaults to 10 seconds.
Use `retries` to control how many times a failed request is retried.

## `upload()`

The `chunk` size defaults to 1024 bytes.

## Limits

Uploads are capped at `MAX_SIZE` of 100 bytes.

## Auth

Call `legacy_login(user)` to sign in.

## FAQ

Set `timeout` to a higher value than the default 10 if requests are slow.
