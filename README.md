# keycloak-script-provider-uploader
Utility to install Keycloak script providers from the command line

## Usage
`python script_provider_uploader.py`

By default, the script will:
* Look for a namespace including the words "domino" and "platform" in your current kubectl context.
* Look for the first Keycloak pod in a statefulSet (i.e. ending `-0`) in that namespace.
* Look for files ending in `-authenticator.js`, `-mapper.js` and `-policy.js` in your current directory.
* Build a .jar file with the appropriate file structure and metadata JSON file.
* Compress the .jar file and copy it to your Keycloak pod.

You can supply any number of Javascript script provider files when you run the updater script– you don't have to have an authenticator, a mapper and a policy.

## Customisation
If your Keycloak instance does not run in a namespace that includes both `domino` and `platform`, you can override this with the environment variable `KEYCLOAK_NAMESPACE`.

`export KEYCLOAK_NAMESPACE=keycloak-namespace; python script_provider_uploader.py`

You specify another directory for your Javascript script providers like so:
`python script_provider_uploader.py /path/to/javascript/files`
The path can be relative to the uploader script (`./javascript/files`) or absolute, as above.
