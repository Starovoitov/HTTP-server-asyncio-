Asynchronous http server. Uses asyncore - the server is dispatcher,
http handler is separate class (async_chat) and sending content via fifo producer (ContentProducer class)
 Can work in several workers (the default is 10). In current realization supports only http/1.0 without cgi, ssl and only for GET, HEAD, POST methods
Parameters description:
-h (--help) - print help
-r (--root) - set server root directiry for content storing. Default is /var/www/html
-p (--port) - listening port for the server. Default is 8080
-i (--interface) - interface for listening socket of the server. Default is 0.0.0.0 (all available)
-l (--log) - path for logging. Default is console output
-w (--workers) - number of process instances (workers) of the server. Default is 10
--forbidden_methods - http methods banned for the server (http code 405 will be send). (like POST)

Example of using:

    python httpd.py -p 8080 --interface=0.0.0.0 -w 10 --forbidden_methods=POST


Simple load test:

    ab -c 100 -n 50000 -r http://localhost:8080/

Results:

    Server Software:        Linux
    Server Hostname:        localhost
    Server Port:            8080

    Document Path:          /
    Document Length:        11321 bytes

    Concurrency Level:      100
    Time taken for tests:   9.988 seconds
    Complete requests:      50000
    Failed requests:        0
    Total transferred:      575200000 bytes
    HTML transferred:       566050000 bytes
    Requests per second:    5006.09 [#/sec] (mean)
    Time per request:       19.976 [ms] (mean)
    Time per request:       0.200 [ms] (mean, across all concurrent requests)
    Transfer rate:          56240.30 [Kbytes/sec] received

    Connection Times (ms)
                  min  mean[+/-sd] median   max
    Connect:        0   13 120.7      1    3041
    Processing:     0    6   6.3      4     417
    Waiting:        0    3   5.6      2     416
    Total:          0   19 122.0      5    3442

    Percentage of the requests served within a certain time (ms)
    50%      5
    66%      7
    75%      9
    80%     10
    90%     13
    95%     16
    98%     23
    99%   1016
    100%   3442 (longest request)
