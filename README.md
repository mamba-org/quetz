Quetz
=====

Usage
-----

Create environment:
```
mamba create -n quetz -c conda-forge python fastapi authlib httpx=0.12.0 sqlalchemy sqlite \
python-multipart uvicorn

conda activate quetz
```

Initialize environment variables:
```
source ./set_env_dev.sh
```

Initialize test database:
```
python init_db.py
```

Run the fastapi server:
```
uvicorn quetz.main:app --reload
```

Links:
 * http://localhost:8000/static/index.html - Login with your github account
 * http://localhost:8000/dummylogin/[ alice | bob | carol | dave] - Login with test user
 * http://localhost:8000/docs - Swagger UI for this REST service

Run test CLI client:
```
./test-cli-client.sh
```

This uploads `testupload.txt` to `./files/Channel 0/Package 0/`
