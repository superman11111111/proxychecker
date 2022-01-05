# ProxyChecker - Threaded Proxy Checker with anonymity checks

Check proxies.txt and serve list of working ones at /api/working

### /api/working

GET Parameters:

- type: str # Type of proxy to return (Currently either [all, anon], not optional)

### /api/headers

Returns the headers of the request sent by the client (not json).

### Anonymity Checking

Requests /api/headers over proxy, if headers contain X-Forwarded-For, proxy no good

## TODO

- Need more indicators of anonymity? (Don't know anymore tbh)
- too many open files error, not really an issue but maybe needs fix in future
- Flask kinda unsafe lol who cares
