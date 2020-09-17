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

The quetz project is an open source server for conda packages.
It is built upon FastAPI with an API-first approach.
A quetz server can have many users, channels and packages.
With quetz, fine-grained permissions on channel and package-name level will be possible.

Quetz also comes with the `quetz-client` that can be used to upload packages to a quetz server instance.

## Usage

You should have [mamba](https://github.com/mamba-org/mamba) or conda installed.

Then create an environment:

```
mamba create -n quetz -c conda-forge 'python>=3.7' fastapi typer authlib httpx=0.12.0 sqlalchemy sqlite \
python-multipart uvicorn zstandard conda-build appdirs toml quetz-client fsspec

conda activate quetz
```

Get `Quetz` sources:

```
mkdir quetz
git clone https://github.com/TheSnakePit/quetz.git quetz
```

Install `Quetz`:

> Use the editable mode `-e` if you are developer and want to take advantage of the `reload` option of `Quetz`

```
pip install -e quetz
```

Use the CLI to create a `Quetz` instance:

```
quetz run test_quetz --copy-conf ./dev_config.toml --dev --reload
```

Links:
 * http://localhost:8000/ - Login with your github account
 * http://localhost:8000/api/dummylogin/alice  - Login with test user, one of [alice | bob | carol | dave]
 * http://localhost:8000/docs - Swagger UI for this REST service

Download `xtensor` as test package:
```
./download-test-package.sh
```

Run test upload using quetz-client. (For testing purposes, an API key is created for the test user "alice" at server launch and is printed to the terminal, so use that for this example):

```
export QUETZ_API_KEY=E_KaBFstCKI9hTdPM7DQq56GglRHf2HW7tQtq6si370
quetz-client http://localhost:8000/api/channels/channel0 xtensor/linux-64/xtensor-0.16.1-0.tar.bz2 xtensor/osx-64/xtensor-0.16.1-0.tar.bz2
```

Install the test package with conda:

```
mamba install --strict-channel-priority -c http://localhost:8000/channels/channel0 -c conda-forge xtensor
```

Output:

```
...
  Package  Version  Build          Channel                                                     Size
─────────────────────────────────────────────────────────────────────────────────────────────────────
  Install:
─────────────────────────────────────────────────────────────────────────────────────────────────────

  xtensor   0.16.1  0              http://localhost:8000/channels/channel0/osx-64            109 KB
  xtl       0.4.16  h04f5b5a_1000  conda-forge/osx-64                                         47 KB

  Summary:

  Install: 2 packages

  Total download: 156 KB

─────────────────────────────────────────────────────────────────────────────────────────────────────
...
```

Browse channels:

```
http://localhost:8000/channels/channel0/
```

## S3 Backend

To enable the S3 backend, you will first require the s3fs library:

    mamba install -c conda-forge s3fs

Then add your access and secret keys to the `s3` section with your
`config.toml`, like so:

```
[s3]
access_key = "AKIAIOSFODNN7EXAMPLE"
secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
url = "https://..."
bucket_prefix="..."
bucket_suffix="..."
```

Be sure to set the url field if not using AWS.

Channels are created with the following semantics:
```
{bucket_prefix}{channel_name}{bucket_suffix}
```
The s3 backend is currently designed for one bucket per channel. It may be possible to put all channels in one bucket, but that will require some code tweaks

If you're using IAM roles, dont set `access_key` and `secret_key` or set them to empty strings `""`.

## Google OAuth 2.0 OpenID Connect

To enable auth via Google, you will need to register an application at: https://console.developers.google.com/apis/credentials

Then add the client secret & ID to a `google` section of your `config.toml`:

```
[google]
client_id = "EXAMPLEID420127570681-6rbcgdj683l3odc3nqearn2dr3pnaisq.apps.googleusercontent.com"
client_secret = "EXAMPLESECRETmD-7UXVCMZV3C7b-kZ9yf70"
```

## Frontend

Quetz comes with a initial frontend implementation. It can be found in quetz_frontend.
To build it, one needs to install:

```
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

A proxy channel "mirrors" another channel usually from a different server, so that the packages can be installed from the proxy as if they were installed from the proxied channel. The reason to use the proxy channel is that it can cache downloaded packages locally (limitting traffic to the server of origin) or that the quetz server can be located behind a corporate firewall. 


To create the channel use the properties `mirror_channel_url=URL_TO_SOURCE_CHANNEL` and `mirror_mode='proxy'` in the POST method of /api/channels endpoint:

```
{
  "name": "proxy-channel",
  "private": false,
  "mirror_channel_url": "https://conda.anaconda.org/btel",
  "mirror_mode": "proxy"
}
```

```
curl -X POST "http://localhost:8000/api/channels" \
    -H  "accept: application/json" \
    -H  "Content-Type: application/json" \
    -H  "X-API-Key: fe0fc856cdd44e93b6e43ec09e421663" \
    -d '{"name":"proxy-channel",
         "private":false,
         "mirror_channel_url":"https://conda.anaconda.org/btel",
         "mirror_mode":"proxy"}'
```

where the `X-API-Key` is the API key that was created for you the first time you started a new deployment.

Then you can install packages from the channel the standard way using `conda` or `mamba`:

```
mamba install --strict-channel-priority -c http://localhost:8000/channels/proxy-channel nrnpython
```

### Create a mirroring channel

A mirror channel is an exact copy of another channel possibly from a different (anaconda or quetz) server. The packages are downloaded from the server and added to the mirror channel. The mirror channel supports all standard API request except the request that would modify the packages.

Creating a mirror channel is similar to creating the proxy channel described above except that you need to change the `mirror_mode` from `proxy` to `mirror` (and choose more suitable channel name obviously).
