import json
import os
import shutil
import sys
import tarfile
from kubernetes import client, config
from kubernetes.stream import stream
from tempfile import TemporaryFile

destination_directory: str = "/opt/jboss/keycloak/standalone/deployments/keycloak-resources"
destination_jarfile: str = "custom_script_providers.jar"
keycloak_version: str = "18"


class KeycloakPods:
    def __init__(self):
        self.namespace: str = ""
        self.names = []


def find_keycloak_pods(namespace):
    if namespace != "":
        kcp.namespace = namespace
    else:
        for i in v1.list_namespace().items:
            if "domino" in i.metadata.name and "platform" in i.metadata.name:
                kcp.namespace = i.metadata.name
                print(f"Domino platform namespace: {kcp.namespace}")
                break
    if kcp.namespace == "":
        print("Domino platform namespace not found")
        exit(1)

    for pod in v1.list_namespaced_pod(namespace=kcp.namespace).items:
        keycloak_pod_name = "keycloakv" + keycloak_version
        if pod.metadata.name.startswith(keycloak_pod_name):
            kcp.names.append(pod.metadata.name)
            print(f"Keycloak pod: {pod.metadata.name}")
    if not kcp.names:
        print("Keycloak pod not found")
        exit(1)
    print(kcp.names)


def build_jar():
    # create a JAR file with the following structure:
    # META-INF/keycloak-scripts.json
    # *-authenticator.js
    # *-mapper.js
    # *-policy.js

    if os.path.exists(destination_jarfile):
        os.remove(destination_jarfile)
    if os.path.exists(jar_folder):
        shutil.rmtree(jar_folder)
    os.makedirs(metadata_folder, exist_ok=True)

    authenticator_scripts = []
    mapper_scripts = []
    policy_scripts = []

    for file in os.listdir(source_directory):
        if not file.endswith(".js"):
            continue
        elif file.endswith("-authenticator.js"):
            authenticator_dict = {"name": file.split("-authenticator.js", 1)[0], "fileName": file, "description": file}
            print(f"Found authenticator script: {file}")
            authenticator_scripts.append(authenticator_dict)
        elif file.endswith("-mapper.js"):
            mapper_dict = {"name": file.split("-mapper.js", 1)[0], "fileName": file, "description": file}
            print(f"Found mapper script: {file}")
            mapper_scripts.append(mapper_dict)
        elif file.endswith("-policy.js"):
            policy_dict = {"name": file.split("-policy.js", 1)[0], "fileName": file, "description": file}
            print(f"Found policy script: {file}")
            policy_scripts.append(policy_dict)
        shutil.copyfile(os.path.join(source_directory, file), os.path.join(jar_folder, file))

    keycloak_scripts_dict = {}
    if len(authenticator_scripts) > 0:
        keycloak_scripts_dict["authenticators"] = authenticator_scripts
    if len(mapper_scripts) > 0:
        keycloak_scripts_dict["mappers"] = mapper_scripts
    if len(policy_scripts) > 0:
        keycloak_scripts_dict["policies"] = policy_scripts
    if len(keycloak_scripts_dict) == 0:
        print("No script providers found")
        shutil.rmtree(jar_folder)
        exit(1)

    # serialise json
    json_object = json.dumps(keycloak_scripts_dict, indent=4)
    print("Metadata for jar file:", json_object)

    # generate keycloak-scripts.json metadata file
    with open(metadata_file, "w") as outfile:
        outfile.write(json_object)

    # zip contents of jar_folder, remove ".zip" suffix, and clean up jar_folder
    shutil.make_archive(destination_jarfile, 'zip', jar_folder)
    shutil.move(destination_jarfile + ".zip", destination_jarfile)
    shutil.rmtree(jar_folder)


def copy_jar_to_keycloak():
    for keycloak_pod in kcp.names:
        exec_command = ['tar', 'xvf', '-', '-C', destination_directory]
        resp = stream(v1.connect_get_namespaced_pod_exec, keycloak_pod, kcp.namespace,
                      command=exec_command,
                      stderr=True, stdin=True,
                      stdout=True, tty=False,
                      _preload_content=False)

        with TemporaryFile() as tar_buffer:
            with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
                tar.add(destination_jarfile)

            tar_buffer.seek(0)
            commands = [tar_buffer.read()]

            while resp.is_open():
                resp.update(timeout=1)
                if resp.peek_stdout():
                    print("STDOUT: %s" % resp.read_stdout())
                if resp.peek_stderr():
                    print("STDERR: %s" % resp.read_stderr())
                if commands:
                    c = commands.pop(0)
                    resp.write_stdin(c)
                else:
                    break
            resp.close()


def main():
    build_jar()

    find_keycloak_pods(keycloak_namespace)

    copy_jar_to_keycloak()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        source_directory = os.getcwd()
    else:
        source_directory: str = sys.argv[1]

    if os.getenv("KEYCLOAK_NAMESPACE") is not None:
        keycloak_namespace: str = os.getenv("KEYCLOAK_NAMESPACE")
        print(f"KEYCLOAK_NAMESPACE variable found: {keycloak_namespace}")
    else:
        keycloak_namespace: str = ""

    jar_folder = os.path.join(source_directory, "jar")
    metadata_folder = os.path.join(jar_folder, "META-INF")
    metadata_file = os.path.join(metadata_folder, "keycloak-scripts.json")

    print(f"Destination directory in Keycloak: {destination_directory}")
    print(f"Script provider jar file: {destination_jarfile}")

    config.load_kube_config()
    v1 = client.CoreV1Api()

    kcp = KeycloakPods()

    main()
