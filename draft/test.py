import requests

headers = {
    "x-api-key": "PHUOzk63mMI6iFqWhUBq2r7ZwrITdVoqL9oSnGfQ"
}

response = requests.get(
    "https://api-op.grid.gg/file-download/end-state/grid/series/1234556",
    headers = headers
)

print(response)