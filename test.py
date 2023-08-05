data = [
    {"domain": "1.api-fanqienovel.sunianyun.live", "timestamp": 1691196636.3512049, "load": 1},
    {"domain": "2.api-fanqienovel.sunianyun.live", "timestamp": 1691196636.3512049, "load": 2},
    {"domain": "3.api-fanqienovel.sunianyun.live", "timestamp": 1691196636.3512049, "load": 3},
]

print(data)
a = data.copy()
data.append({"domain": "4.api-fanqienovel.sunianyun.live", "timestamp": 1691196636.3512049, "load": 4})
a.sort(key=lambda x: x.get('load', 0))
print(a)
print(data)