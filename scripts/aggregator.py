MY_API_KEY = "replace-with-API-key"

import os
import json
import io
import urllib2
import copy

# The tracked AP items, which were changed with 5.13
AP_ITEM_NAMES = {"Blasting Wand", "Needlessly Large Rod", "Rabadon's Deathcap", "Zhonya's Hourglass", "Luden's Echo", "Rylai's Crystal Scepter", "Archangel's Staff", "Rod of Ages", "Haunting Guise", "Liandry's Torment", "Void Staff", "Nashor's Tooth", "Will of the Ancients", "Morellonomicon", "Athene's Unholy Grail"}

print("Getting static champion data...")
response = urllib2.urlopen("https://global.api.pvp.net/api/lol/static-data/na/v1.2/champion?dataById=true&api_key=" + MY_API_KEY)
CHAMP_DATA = json.loads(response.read())["data"]

# A json-style dictionary: STATS[5.11/5.14][normal/ranked][champion/all][mageCount/totalCount/item][itemBuilderCount/itemSellerCount/itemBuildTimeSum/itemPriorityScoreSum]
STATS = {"5.11":{"normal":{}, "ranked":{}}, "5.14":{"normal":{}, "ranked":{}}}

itemStructure = {"mageCount":0, "totalCount":0}
for itemName in AP_ITEM_NAMES:
    itemStructure[itemName] = {"builderCount":0, "sellerCount":0, "buildTimeSum":0, "priorityScoreSum":0}
for champKey in CHAMP_DATA.keys():
    name = CHAMP_DATA[champKey]["name"]
    STATS["5.11"]["normal"][name] = copy.deepcopy(itemStructure)
    STATS["5.11"]["ranked"][name] = copy.deepcopy(itemStructure)
    STATS["5.14"]["normal"][name] = copy.deepcopy(itemStructure)
    STATS["5.14"]["ranked"][name] = copy.deepcopy(itemStructure)

# This script combines all json files in the folder "partial stats"
for statsFile in os.listdir("partial stats/"):
    partialStats = json.load(io.open("partial stats/" + statsFile))
    print(statsFile)
    for versionKey in STATS:
        versionDict = STATS[versionKey]
        for typeKey in versionDict:
            typeDict = versionDict[typeKey]
            for champKey in typeDict:
                champDict = typeDict[champKey]
                champDict["mageCount"] += partialStats[versionKey][typeKey][champKey]["mageCount"]
                champDict["totalCount"] += partialStats[versionKey][typeKey][champKey]["totalCount"]
                for itemKey in champDict:
                    if itemKey not in {"mageCount", "totalCount"}:
                        itemDict = champDict[itemKey]
                        itemDict["builderCount"] += partialStats[versionKey][typeKey][champKey][itemKey]["builderCount"]
                        itemDict["sellerCount"] += partialStats[versionKey][typeKey][champKey][itemKey]["sellerCount"]
                        itemDict["buildTimeSum"] += partialStats[versionKey][typeKey][champKey][itemKey]["buildTimeSum"]
                        itemDict["priorityScoreSum"] += partialStats[versionKey][typeKey][champKey][itemKey]["priorityScoreSum"]




writePath = "stats.json"
# Write stats to a json file
stream = open(writePath, 'w')
json.dump(STATS, stream)
stream.close()
print("Done!")
