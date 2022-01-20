![quetz header image](docs/assets/quetz_header.png)

## The Open-Source Server for Conda Packages

<table>
<thead align="center" cellspacing="10">
  <tr>
    <th colspan="3" align="center" border="">part of mamba-org</th>
  </tr>
</thead>
<tbody>
  <tr background="#FFF">
    <td align="center">Package Manager <a href="https://github.com/mamba-org/mamba">mamba</a></td>
    <td align="center">Package Server <a href="https://github.com/mamba-org/quetz">quetz</a></td>
    <td align="center">Package Builder <a href="https://github.com/mamba-org/boa">boa</a></td>
  </tr>
</tbody>
</table>

# Quetz

[![Documentation Status](https://readthedocs.org/projects/quetz/badge/?version=latest)](https://quetz.readthedocs.io/en/latest/?badge=latest)

The quetz project is an open source server for conda packages.
It is built upon FastAPI with an API-first approach.
A quetz server can have many users, channels and packages.
With quetz, fine-grained permissions on channel and package-name level will be possible.

Quetz has an optional client `quetz-client` that can be used to upload packages to a quetz server instance.

## Usage

You should have [mamba](https://github.com/mamba-org/mamba) or conda installed.

Get `Quetz` sources:

```bash
git clone https://github.com/mamba-org/quetz.git
```

Then create an environment:

```bash
cd quetz
mamba env create -f environment.yml
conda activate quetz
```

Install `Quetz`:

> Use the editable mode `-e` if you are developer and want to take advantage of the `reload` option of `Quetz`

```bash
pip install -e .
```

Use the CLI to create a `Quetz` instance:

```bash
quetz run test_quetz --copy-conf ./dev_config.toml --dev --reload
```

Links:

* <http://localhost:8000/> - Login with your github account
* <http://localhost:8000/api/dummylogin/alice>  - Login with test user, one of [alice | bob | carol | dave]
* <http://localhost:8000/docs> - Swagger UI for this REST service

Download `xtensor` as test package:

```bash
./download-test-package.sh
```

Run test upload using quetz-client. (For testing purposes, an API key is created for the test user "alice" at server launch and is printed to the terminal, so use that for this example):

```bash
export QUETZ_API_KEY=E_KaBFstCKI9hTdPM7DQq56GglRHf2HW7tQtq6si370
quetz-client http://localhost:8000/api/channels/channel0 xtensor/linux-64/xtensor-0.16.1-0.tar.bz2 xtensor/osx-64/xtensor-0.16.1-0.tar.bz2
```

Install the test package with conda:

```bash
mamba install --strict-channel-priority -c http://localhost:8000/get/channel0 -c conda-forge xtensor
```

Output:

```text
...
  Package  Version  Build          Channel                                                     Size
─────────────────────────────────────────────────────────────────────────────────────────────────────
  Install:
─────────────────────────────────────────────────────────────────────────────────────────────────────

  xtensor   0.16.1  0              http://localhost:8000/get/channel0/osx-64                 109 KB
  xtl       0.4.16  h04f5b5a_1000  conda-forge/osx-64                                         47 KB

  Summary:

  Install: 2 packages

  Total download: 156 KB

─────────────────────────────────────────────────────────────────────────────────────────────────────
...
```

Browse channels: <http://localhost:8000/get/channel0/>

## S3 Backend

To enable the S3 backend, you will first require the s3fs library:

```bash
mamba install -c conda-forge s3fs
```

Then add your access and secret keys to the `s3` section with your
`config.toml`, like so:

```ini
[s3]
access_key = "AKIAIOSFODNN7EXAMPLE"
secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
url = "https://..."
region = ""
bucket_prefix="..."
bucket_suffix="..."
```

Be sure to set the url and region field if not using AWS.

Channels are created with the following semantics:

```text
{bucket_prefix}{channel_name}{bucket_suffix}
```

The s3 backend is currently designed for one bucket per channel. It may be possible to put all channels in one bucket, but that will require some code tweaks

If you're using IAM roles, dont set `access_key` and `secret_key` or set them to empty strings `""`.

## Google OAuth 2.0 OpenID Connect

To enable auth via Google, you will need to register an application at: <https://console.developers.google.com/apis/credentials>

Then add the client secret & ID to a `google` section of your `config.toml`:

```ini
[google]
client_id = "EXAMPLEID420127570681-6rbcgdj683l3odc3nqearn2dr3pnaisq.apps.googleusercontent.com"
client_secret = "EXAMPLESECRETmD-7UXVCMZV3C7b-kZ9yf70"
```

## PostgreSQL

By default, quetz will run with sqlite database, which works well for local tests and small local instances. However, if you plan to run quetz in production, we recommend to configure it with the PostgreSQL database. There are several options to install PostgreSQL server on your local machine or production server, one of them being the official PostgreSQL docker image.

### Running PostgreSQL server with docker

You can the PostgresSQL image from the docker hub and start the server with the commands:

```bash
docker pull postgres
docker run --name some-postgres -p 5432:5432 -e POSTGRES_PASSWORD=mysecretpassword -d postgres
```

This will start the server with the user `postgres` and the password `mysecretpassword` that will be listening for connection on the port 5432 of localhost.

You can then create a database in PostgreSQL for quetz tables:

```bash
sudo -u postgres psql -h localhost -c 'CREATE DATABASE quetz OWNER postgres;'
```

### Deploying Quetz with PostgreSQL backend

Then in your configuration file (such as `dev_config.toml`) replace the `[sqlalchemy]` section with:

```ini
[sqlalchemy]
database_url = "postgresql://postgres:mysecretpassword@localhost:5432/quetz"
```

Finally, you can create and run a new quetz deployment based on this configuration (we assume that you saved it in file `config_postgres.toml`):

```bash
quetz run postgres_quetz --copy-conf config_postgres.toml 
```

Note that this recipe will create an ephemeral PostgreSQL database and it will delete all data after the `some-postgres` container is stopped and removed. To make the data persistent, please check the documentation of the `postgres` [image](https://hub.docker.com/_/postgres/)  or your container orchestration system (Kubernetes or similar).

### Running tests with PostgreSQL backend

To run the tests with the PostgreSQL database instead of the default SQLite, follow the steps [above](#running-postgresql-server-with-docker) to start the PG server. Then create an new database:

```bash
psql -U postgres -h localhost -c 'CREATE DATABASE test_quetz OWNER postgres;'
```

You will be asked to type the password to the DB, which you defined when starting your PG server. In the docker-based instructions above, we set it to `mysecretpassword`.

To run the tests with this database you need to configure the `QUETZ_TEST_DATABASE` environment variable:

```bash
QUETZ_TEST_DATABASE="postgresql://postgres:mysecretpassword@localhost:5432/test_quetz" pytest -v ./quetz/tests
```

## Frontend

Quetz comes with a initial frontend implementation. It can be found in quetz_frontend.
To build it, one needs to install:

```bash
mamba install 'nodejs>=14'
cd quetz_frontend
npm install
npm run build
# for development
npm run watch
```

This will build the javascript files and place them in `/quetz_frontend/dist/` from where they are automatically picked up by the quetz server.

## License

We use a shared copyright model that enables all contributors to maintain the copyright on their contributions.

This software is licensed under the BSD-3-Clause license. See the [LICENSE](LICENSE) file for details.

## Using quetz

### Create a channel

First, make sure you're logged in to the web app.

Then, using the swagger docs at `<deployment url>:<port>/docs`, POST to `/api/channels` with the name and description of your new channel:

```json
{
  "name": "my-channel",
  "description": "Description for my-channel",
  "private": false
}
```

This will create a new channel called `my-channel` and your user will be the Owner of that channel.

### Generate an API key

API keys are scoped per channel, per user and optionally per package.
In order to generate an API key the following must be true:

1. First, make sure you're logged in to the web app.
2. The user must be part of the target channel (you might need to create a channel first, see the previous section on how to create a channel via the swagger docs)
3. Go to the swagger docs at `<deployment url>:<port>/docs` and POST to `/api/api-keys`:

    ```json
    {
      "description": "my-test-token",
      "roles": [
        {
          "role": "owner",
          "channel": "my-channel"
        }
      ]
    }
    ```

4. Then, GET on `/api/api-keys` to retrieve your token
5. Finally, set this value to QUETZ_API_KEY so you can use quetz-client to interact with the server.

### Create a proxy channel

A proxy channel "mirrors" another channel usually from a different server, so that the packages can be installed from the proxy as if they were installed directly from that server. All downloaded packages are cached locally and the cache is always up to date (there is no risk of serving stale packages). The reason to use the proxy channel is to limit traffic to the server of origin or to serve a channel that could be inaccessible from behind the corporate firewall.

To create a proxy channel use the properties `mirror_channel_url=URL_TO_SOURCE_CHANNEL` and `mirror_mode='proxy'` in the POST method of `/api/channels` endpoint. For example, to proxy the channel named `btel` from anaconda cloud server, you might use the following request data:

```json
{
  "name": "proxy-channel",
  "private": false,
  "mirror_channel_url": "https://conda.anaconda.org/btel",
  "mirror_mode": "proxy"
}
```

You may copy the data directly to the Swagger web interface under the heading POST `/api/channels` or use the cURL tool from command line. Assuming that you deployed a quetz server on port 8000 (the default) on your local machine, you could make the request with the following cURL command:

```bash
export QUETZ_API_KEY=...
curl -X POST "http://localhost:8000/api/channels" \
    -H  "accept: application/json" \
    -H  "Content-Type: application/json" \
    -H  "X-API-Key: ${QUETZ_API_KEY}" \
    -d '{"name":"proxy-channel",
         "private":false,
         "mirror_channel_url":"https://conda.anaconda.org/btel",
         "mirror_mode":"proxy"}'
```

where the value of `QUETZ_API_KEY` variable should be the API key that was printed when you created the quetz deployment or retrieved using the API as described in the section [Generate an API key](#generate-an-api-key).

Then you can install packages from the channel the standard way using `conda` or `mamba`:

```bash
mamba install --strict-channel-priority -c http://localhost:8000/get/proxy-channel nrnpython
```

### Create a mirroring channel

A mirror channel is an exact copy of another channel usually from a different (anaconda or quetz) server. The packages are downloaded from that server and added to the mirror channel. The mirror channel supports the standard Quetz API except requests that would add or modify the packages (POST `/api/channels/{name}/files`, for example). Mirror channels can be used to off load traffic from the primary server, or to create a channel clone on the company Intranet.

Creating a mirror channel is similar to creating proxy channels except that you need to change the value of `mirror_mode` attribute from `proxy` to `mirror` (and choose a more suitable channel name obviously):

```json
{
  "name": "mirror-channel",
  "private": false,
  "mirror_channel_url": "https://conda.anaconda.org/btel",
  "mirror_mode": "mirror"
}
```

or with cURL:

```bash
export QUETZ_API_KEY=...
curl -X POST "http://localhost:8000/api/channels" \
    -H  "accept: application/json" \
    -H  "Content-Type: application/json" \
    -H  "X-API-Key: ${QUETZ_API_KEY}" \
    -d '{"name":"mirror-channel",
         "private":false,
         "mirror_channel_url":"https://conda.anaconda.org/btel",
         "mirror_mode":"mirror"}'
```

Mirror channels are read only (you can not add or change packages in these channels), but otherwise they are fully functional Quetz channels and support all standard read (GET) operations. For example, you may list all packages using GET `/api/channels/{channel_name}/packages` endpoint:

```bash
curl http://localhost:8000/api/channels/mirror-channel/packages
```

If packages are added or modified on the primary server from which they were pulled initially, they won't be updated automatically in the mirror channel. However, you can trigger such synchronisation manually using the PUT `/api/channels/{channel_name}/actions` endpoint:

```bash
curl -X PUT localhost:8000/api/channels/mirror-channel/actions \
   -H "X-API-Key: ${QUETZ_API_KEY}" \
   -d '{"action": "synchronize"}'
```

Only channel owners or maintainers are allowed to trigger synchronisation, therefore you have to provide a valid API key of a privileged user.
