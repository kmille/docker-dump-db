# docker-dump

A python script that dumps/backups all database containers running on a Docker host.

## What is it doing?

- Iterates over all running containers
- check if the image of the container contains: mariadb|mysql|postgres
- if so, dump the database (mysqldump|pg_dumpall)


## NOT SO NICE
If we don't use `stream=True` in `exec_run`, the process runs out of memory if big databases are dumped (whole dump needs to be in the RAM).  
But if we use stream=True, we don't get the return value of msqldump|pg_dupm, see: https://github.com/docker/docker-py/issues/1989
So I manually check if if the dump worked ...

## How to use it

If you call it without a parameter, all databases are dumped.

```bash
[root@backup-scripts]# ./docker-dump.py -h
usage: 
       [-h] [-e EXCLUDE_CONTAINER [EXCLUDE_CONTAINER ...]] [-i INCLUDE_CONTAINER]
optional arguments:
  -h, --help            show this help message and exit
  -e EXCLUDE_CONTAINER [EXCLUDE_CONTAINER ...], --exclude-container EXCLUDE_CONTAINER [EXCLUDE_CONTAINER ...]
                        exclude a specific container (can be used multiple times)
  -i INCLUDE_CONTAINER, --include-container INCLUDE_CONTAINER
                        only backup specific ontainer
```

## Handling corner cases

Normally, the tool get's the DB user/password/db out of the environment variable. If you have multiple databases in Container, you can specify this by configuring the CORNER_CASE_CONTAINER variable.

```json
CORNER_CASE_CONTAINER = [
    {                                                                                                                  
        "container_name": "icinga_mariadb_1",
        "type": "mariadb",                                 
        "container_dir": "/opt/icinga",                                                                                
        "database": "icinga",                                                                                          
        "user": "root",
        "password": "changeme",                          
    },                                                                                                                 
] 
```



