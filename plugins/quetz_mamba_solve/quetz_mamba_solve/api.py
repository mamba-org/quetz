import json

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from .solver import MambaSolver

router = APIRouter()


def parse_list(names):
    """
    accepts strings formatted as lists with square brackets
    names can be in the format
    "[bob,jeff,greg]" or '["bob","jeff","greg"]'
    """

    def remove_prefix(text: str, prefix: str):
        if text.startswith(prefix):
            text = text[len(prefix) :]  # noqa: E203
        return text

    def remove_postfix(text: str, postfix: str):
        if text.endswith(postfix):
            text = text[: -len(postfix)]
        return text

    if names is None:
        return

    # we already have a list, we can return
    if isinstance(names, list):
        return names

    # if we don't start with a "[" and end with "]" it's just a normal entry
    if not names.startswith("[") and not names.endswith("]"):
        return [names]

    names = remove_prefix(names, "[")
    names = remove_postfix(names, "]")

    names_list = names.split(",")
    names_list = [remove_prefix(n.strip(), "\"") for n in names_list]
    names_list = [remove_postfix(n.strip(), "\"") for n in names_list]

    return names_list


@router.get(
    "/api/mamba/solve/{channels}/{subdir}/{spec}", response_class=PlainTextResponse
)
def mamba_solve(channels, subdir, spec):
    channels = parse_list(channels)
    spec = parse_list(spec)
    s = MambaSolver(channels, subdir)
    _, link, _ = s.solve(spec).to_conda()

    data = []
    data_bytes = f"# platform: {subdir}\n\n"
    data_bytes += "@EXPLICIT\n\n"
    for c, pkg, jsn_s in link:
        jsn_content = json.loads(jsn_s)
        url = jsn_content["url"]
        md5 = jsn_content["md5"]
        each_pkg = f"{url}#{md5}"
        data.append(each_pkg)

    data_bytes += "\n".join(data)

    return data_bytes
