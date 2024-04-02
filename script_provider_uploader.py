import json
import os
import shutil
import sys
import tarfile
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
from tempfile import TemporaryFile

destination_jarfile: str = "custom_script_providers.jar"


class KeycloakPods:
    def __init__(self):
        self.namespace: str = ""
        self.names = []


def find_keycloak_pods(namespace):
    if namespace != "":
        kcp.namespace = namespace
    else:
        for ns in v1.list_namespace(label_selector='domino-platform = true').items:
            kcp.namespace = ns.metadata.name
            print(f"Domino platform namespace: {kcp.namespace}")
            break
    if kcp.namespace == "":
        print("Domino platform namespace not found")
        exit(1)

    for p in v1.list_namespaced_pod(namespace=kcp.namespace, label_selector='app.kubernetes.io/name = keycloak').items:
        kcp.names.append(p.metadata.name)
    if not kcp.names:
        print("Keycloak pod not found")
        exit(1)
    print(f"Keycloak pods found: {kcp.names}")


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
        if "v18" in keycloak_pod:
            destination_directory: str = "/opt/jboss/keycloak/standalone/deployments/keycloak-resources"
        elif "v22" in keycloak_pod:
            destination_directory: str = "/domino/shared/custom-resources/providers"
        elif "v23" in keycloak_pod:
            destination_directory: str = "/domino/shared/custom-resources/providers"

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
        # Restart Keycloak pod to force it to read new jar file
        try:
            api_response = v1.delete_namespaced_pod(keycloak_pod, kcp.namespace)
            print(f"Restarting Keycloak pod to complete copy: %s" % keycloak_pod)
        except ApiException as e:
            print("Exception when calling CoreV1Api->delete_namespaced_pod: %s\n" % e)


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

    config.load_kube_config()
    v1 = client.CoreV1Api()

    kcp = KeycloakPods()

    main()
