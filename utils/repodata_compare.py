import requests

my_headers = {'accept-encoding':'gzip'}

anaconda = requests.get("https://conda.anaconda.org/conda-forge/linux-64/repodata.json", headers=my_headers)
print ("got anaconda")
quetz = requests.get("https://repo.mamba.pm/conda-forge/linux-64/repodata.json", headers=my_headers)
print ("got quetz")

anaconda_json = anaconda.json()
quetz_json = quetz.json()

anaconda_keys = anaconda_json["packages"].keys()
quetz_keys = quetz_json["packages"].keys()

anaconda_keys = set(anaconda_keys)
quetz_keys = set(quetz_keys)

diff = anaconda_keys - quetz_keys
# print(anaconda_keys)
print(diff)

deep_compare_keys = anaconda_keys & quetz_keys

def compare_pkg_rec(a, b):
	keys = a.keys()
	for key in keys:
		ax = a[key]
		if key not in b:
			print(f"Quetz does not have key {key} for {a['name']} {a['version']} {a['build']}")
			continue

		bx = b[key]
		if type(ax) is list:
			ax = sorted(ax)
			bx = sorted(bx)

		if a[key] != b[key]:
			print(f"Quetz has difference for {a['name']} {a['version']} {a['build']}:")
			print(a[key])
			print(b[key])

for k in deep_compare_keys:
	anaconda_dict = anaconda_json["packages"][k]
	quetz_dict = quetz_json["packages"][k]

	compare_pkg_rec(anaconda_dict, quetz_dict)
print(f"Checked {len(deep_compare_keys)}")