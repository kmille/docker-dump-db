#!/usr/bin/env python3
import sys
import logging
from pathlib import Path
import argparse
import docker  # needs: yum install python-docker or pip install docker

OUT_DIR = "/opt/db-dump-backups"

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(format=FORMAT,
                    level=logging.INFO)
client = docker.from_env()

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


def fail(e, exception=False):
    if exception:
        logging.exception(e)
    else:
        logging.error(e)
    sys.exit(1)


def find_postgres_user(envs):
    for env in envs:
        if "POSTGRES_USER" in env:
            user = env.split("POSTGRES_USER=")[1]
            return user
    logging.warning("env POSTGRES_USER not found. Using default 'postgres")
    return "postgres"


def find_mysql_data(envs):
    user = None
    password = None
    database = None

    for env in envs:
        if "MYSQL_USER" in env:
            user = env.split("MYSQL_USER=")[1]
        if "MARIADB_USER" in env:
            user = env.split("MARIADB_USER=")[1]

        if "MYSQL_PASSWORD" in env:
            password = env.split("MYSQL_PASSWORD=")[1]
        if "MARIADB_PASSWORD" in env:
            password = env.split("MARIADB_PASSWORD=")[1]

        if "MYSQL_DATABASE" in env:
            database = env.split("MYSQL_DATABASE=")[1]
        if "MARIADB_DATABASE" in env:
            database = env.split("MARIADB_DATABASE=")[1]

    if not user or not password or not database:
        fail(
            f"MYSQL USER/PASSWORD/DATABASE not found in environment variables of container:\n{envs}")
    return user, password, database


def backup_postgres_container(container_name: str, container_dir: str, postgres_user: str):
    try:
        container = client.containers.get(container_name)
        result = container.exec_run(f"pg_dumpall --username {postgres_user}",
                                    user="postgres",
                                    stream=True)
        out_file = Path(OUT_DIR / Path(container_dir + "_" + container_name + "_postgres.sql"))
        logging.info(f"Dumping postgres database to {out_file}")
        with out_file.open("wb") as f:
            for data in result.output:
                f.write(data)
        with out_file.open("r") as f:
            content = f.read(300)
            if "PostgreSQL database cluster dump" not in content:
                fail(f"Creating dump for container {container_name} failed:\n{content}")
    except:
        fail("Could not create dump of Postgres Container", True)


def backup_mysql_container(container_name: str, container_dir: str, db_type: str, user: str, password: str, db: str):
    try:
        container = client.containers.get(container_name)
        result = container.exec_run(f"mysqldump -u {user} --no-tablespaces {db}",
                                    environment={"MYSQL_PWD": password},
                                    stream=True)
        out_file = Path(OUT_DIR / Path(container_dir + "_" + container.name + f"_{user}_{db_type}.sql"))
        logging.info(f"Dumping {db_type} database to {out_file}")
        with out_file.open("wb") as f:
            for data in result.output:
                f.write(data)
        with out_file.open("r") as f:
            content = f.read(300)
            if not content.lower().startswith(f"-- {db_type} dump"):
                fail(
                    f"Creating dump for container {container_name} failed:\n{content}")
    except:
        fail(f"Could not create dump of {db_type} container", True)


def make_backup(container: docker.models.containers.Container):
    logging.info(f"Start backuping container {container.name}")
    try:
        container_dir = container.attrs['Config']['Labels']['com.docker.compose.project.working_dir'].replace("/", "_")
    except KeyError:
        logging.warning(f"Could not get working_dir of container {container.name}. Using {container.name}")
        container_dir = container.name

    if "postgres" in str(container.image):
        postgres_user = find_postgres_user(container.attrs["Config"]["Env"])
        backup_postgres_container(container.name, container_dir, postgres_user)
    elif "mysql" in str(container.image):
        user, password, database = find_mysql_data(
            container.attrs["Config"]["Env"])
        backup_mysql_container(container.name, container_dir, "mysql", user, password, database)
    elif "mariadb" in str(container.image):
        user, password, database = find_mysql_data(container.attrs["Config"]["Env"])
        backup_mysql_container(container.name, container_dir, "mariadb", user, password, database)
    else:
        fail(
            f"Container not supported: {container.name} with image {str(container.image)}")
    logging.info(f"Done backuping {container.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", "--exclude-container",
                        help="exclude a specific container (can be used multiple times)",
                        action="append",
                        nargs="+")
    parser.add_argument("-i", "--include-container",
                        help="only backup specific ontainer")
    args = parser.parse_args()

    containers = client.containers.list()
    if args and args.include_container:
        logging.info(f"Only dumping containers with '{args.include_container}' in the container name")
        for container in containers:
            if args.include_container in container.name:
                make_backup(container)

    elif args and args.exclude_container:
        for exclude in args.exclude_container:
            if len(exclude) != 1:
                fail("Only one container for -e is allowed. Use -e container1 -e container2")
        args.exclude_container = [e[0] for e in args.exclude_container]
        logging.info(f"Dumping containers which do not contain {args.exclude_container} in the name")
        for container in containers:
            if "postgres" in str(container.image) or "mysql" in str(container.image) or "mariadb" in str(container.image):
                if container.name in args.exclude_container:
                    logging.info(f"Skipping container {container.name}")
                else:
                    make_backup(container)
    else:
        logging.info("Dumping corner case containers")
        for cc in CORNER_CASE_CONTAINER:
            if cc["type"] == "postgres":
                container = client.containers.get(cc["container_name"])
                backup_postgres_container(cc["container_name"], cc["container_dir"], cc["user"])
            elif cc["type"] in ("mysql", "mariadb"):
                backup_mysql_container(cc["container_name"], cc["container_dir"],
                                       cc["type"], cc["user"], cc["password"], cc["database"])
            else:
                fail(f"invalid Type of corner case config:\n{CORNER_CASE_CONTAINER}")

        blacklist = [c["container_name"] for c in CORNER_CASE_CONTAINER]
        logging.info("Dumping all containers found by docker ps")
        for container in containers:
            if container.name in blacklist:
                logging.info(f"Skipping corner case container {container.name}")
                continue
            if "postgres" in str(container.image) or "mysql" in str(container.image) or "mariadb" in str(container.image):
                make_backup(container)


if __name__ == '__main__':
    main()
