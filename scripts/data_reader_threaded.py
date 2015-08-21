MY_API_KEY = "replace-with-API-key"

AP_ITEM_NAMES = {"Blasting Wand", "Needlessly Large Rod", "Rabadon's Deathcap", "Zhonya's Hourglass", "Luden's Echo", "Rylai's Crystal Scepter", "Archangel's Staff", "Rod of Ages", "Haunting Guise", "Liandry's Torment", "Void Staff", "Nashor's Tooth", "Will of the Ancients", "Morellonomicon", "Athene's Unholy Grail"}
ITEM_FINAL_EXCEPTIONS = {"Crystalline Flask":False, "Doran's Ring":False, "Doran's Shield":False, "Doran's Blade":False,
                         "Archangel's Staff":True}

import json
import urllib2
import math
import copy
import io
import os
import time
import threading
import logging
import httplib

logging.basicConfig(level=logging.DEBUG,
                    format='[%(levelname)s] (%(threadName)-10s) %(message)s',
                    )

print("Getting static item data...")
response = urllib2.urlopen("https://global.api.pvp.net/api/lol/static-data/na/v1.2/item?version=5.11.1&itemListData=into,from,tags&api_key=" + MY_API_KEY)
ITEM_DATA_11 = json.loads(response.read())["data"]

response = urllib2.urlopen("https://global.api.pvp.net/api/lol/static-data/na/v1.2/item?version=5.14.1&itemListData=into,from,tags&api_key=" + MY_API_KEY)
ITEM_DATA_14 = json.loads(response.read())["data"]

ITEM_DATA = {"5.11":ITEM_DATA_11, "5.14":ITEM_DATA_14}

print("Getting static champion data...")
response = urllib2.urlopen("https://global.api.pvp.net/api/lol/static-data/na/v1.2/champion?dataById=true&api_key=" + MY_API_KEY)
CHAMP_DATA = json.loads(response.read())["data"]

def getChampName(champId): # (static data) retrieves champion name from ID.
    return CHAMP_DATA[str(champId)]["name"]

def getItemName(itemId, version): # (static data) just like getChampName, except for the version parameter (items in the system seem to vary between versions).
    return ITEM_DATA[version][str(itemId)]["name"]

def itemIsBootEnchant(itemData, version): # given item API fields, return whether the item is a boot enchantment.
    # Each boot enchant builds from a single item: a tier 2 boot.
    # In general, we aren't as interested in things that build from tier 2 boots. In a build order, players fit in tier 2 boots; enchants usually come later.
    if "from" in itemData:
        parentItemData = ITEM_DATA[version][itemData["from"][0]]
        return "tags" in parentItemData and "Boots" in parentItemData["tags"] and parentItemData["name"] != "Boots of Speed"
    else:
        return False
    
def itemIsFinalBuild(itemId, version): # (static data) retrieves item data and determines if the item is a final build item.
    # If not one of the exceptions, final build items:
    #   do not build into anything else, except for tier 2 boots which technically build into enchantments
    #   are not consumable
    #   are not trinkets
    #   are not boot enchantments (technically final, but the tier 2 of the boot is a better timer of when upgraded boots fill an inventory slot)
    # Exceptions include starting items that don't build into anything and Archangel's Staff (technically not final, but it's what players choose to buy).
    itemData = ITEM_DATA[version][str(itemId)]
    if itemData["name"] in ITEM_FINAL_EXCEPTIONS:
        return ITEM_FINAL_EXCEPTIONS[itemData["name"]]
    else:
        if "tags" in itemData:
            if "Boots" in itemData["tags"]:
                # Either Boots of Speed or tier 2 boots
                return itemData["name"] != "Boots of Speed"
            else:
                return "into" not in itemData and not itemIsBootEnchant(itemData, version) and "Consumable" not in itemData["tags"] and "Trinket" not in itemData["tags"]
        else:
            return "into" not in itemData and not itemIsBootEnchant(itemData, version)

def gameClock(millis): # returns a string in the "12:34" format of the game clock.
    time_seconds,time_minutes = math.modf(millis / 1000.0 / 60.0)
    time_seconds = int(math.floor(time_seconds * 60.0))
    if time_seconds < 10:
        time_seconds = "0" + str(time_seconds)
    else:
        time_seconds = str(time_seconds)
    return str(int(time_minutes)) + ":" + time_seconds

# This script retrieves data from the Riot API and extracts only what is needed for
# the AP item statistics that we're looking at. This boiled-down information is returned as a json-like object.
def getMatchPlayerStats(matchId, matchVersion, regionKey): # For ease of use, match version is given here rather than parsed from match data. (We know from folders which version the matches are.)
    matchData = None
    # Control non-static API call. Rate-limit related 429 errors are not expected; other 429 errors must be handled.
    while matchData is None:
        try:
            response = urllib2.urlopen("https://" + regionKey + ".api.pvp.net/api/lol/" + regionKey + "/v2.2/match/" + str(matchId) + "?includeTimeline=true&api_key=" + MY_API_KEY)
            matchData = json.loads(response.read())
        except urllib2.HTTPError, err:
            if err.code in {429, 500, 503, 504}: # By design and knowing my API rate limit, these 429s only come from server limits.
                logging.debug("[" + regionKey + "] Server error (" + str(err.code) + "), trying again.")
                time.sleep(1.0)
            else:
                raise # Access Denied is 403 and will halt processing here.
        except urllib2.URLError:
            logging.debug("[" + regionKey + "] URL error, trying again.")
        except httplib.IncompleteRead:
            logging.debug("[" + regionKey + "] HTTP read error, trying again.")

    playerDict = {} # playerDict["id"]["champion/isMage/itemsBuilt"]["itemName"]["timestamp/buildPosition"]
    playerBuildCounters = {}
    for participant in matchData["participants"]:
        playerId = participant["participantId"]
        playerDict[playerId] = {"champion":getChampName(participant["championId"]), "isMage":False, "itemsBuilt":{}, "itemsSold":set([])}
        playerBuildCounters[playerId] = 0

    for frame_index in xrange(len(matchData["timeline"]["frames"])):
        frame = matchData["timeline"]["frames"][frame_index]
        if "events" in frame:
            for event_index in xrange(len(frame["events"])):
                event = frame["events"][event_index]
                
                if event["eventType"] == "ITEM_PURCHASED":
                    playerId = event["participantId"]
                    if playerId != 0:
                        itemId = event["itemId"]
                        itemName = getItemName(itemId, matchVersion)
                        itemIsFinal = itemIsFinalBuild(itemId, matchVersion)
                        if itemIsFinal:
                            playerBuildCounters[playerId] += 1
                            if itemName in AP_ITEM_NAMES:
                                playerDict[playerId]["isMage"] = True
                                playerDict[playerId]["itemsBuilt"][itemName] = {"timestamp":event["timestamp"], "priorityScore":playerBuildCounters[playerId]}
                            
                        else:
                            if itemName in AP_ITEM_NAMES:
                                playerDict[playerId]["isMage"] = True
                                playerDict[playerId]["itemsBuilt"][itemName] = {"timestamp":event["timestamp"]}
                            
                        

                                                                        
                elif event["eventType"] == "ITEM_SOLD":
                    playerId = event["participantId"]
                    if playerId != 0:
                        itemId = event["itemId"]
                        itemName = getItemName(itemId, matchVersion)
                        if itemName in AP_ITEM_NAMES:
                            playerDict[playerId]["itemsSold"].add(itemName)
                        
    # Calculate priority scores. An item with a score of 1 was built first by a player; 0 means it was built last.
    for playerId in playerDict:
        playerItemsBuilt = playerDict[playerId]["itemsBuilt"]
        for item in playerItemsBuilt:
            if "priorityScore" in playerItemsBuilt[item]:
                itemsCount = playerBuildCounters[playerId]
                if itemsCount < 6:
                    # The player didn't build a full inventory's worth of items.
                    # Weigh the items that the player built against the remaining unknown items that would've completed the build.
                    playerItemsBuilt[item]["priorityScore"] = 1 - ((playerItemsBuilt[item]["priorityScore"] - 1) / 5.0)
                else:
                    # The player built a full inventory's worth of items, or more.
                    # The scores are normalized.
                    playerItemsBuilt[item]["priorityScore"] = 1 - ((playerItemsBuilt[item]["priorityScore"] - 1) / (itemsCount - 1.0))
    return playerDict

def putStats(statsDict, matchId, matchVersion, matchType, regionKey):
    # Get the match stats.
    matchDict = getMatchPlayerStats(matchId, matchVersion, regionKey)
    # Commit the match data to the given stats table.
    for playerId in matchDict:
        player = matchDict[playerId]
        selectedChampionStats = statsDict[matchVersion][matchType][player["champion"]]
        selectedChampionStats["totalCount"] += 1
        if player["isMage"]:
            selectedChampionStats["mageCount"] += 1
        for soldItemName in player["itemsSold"]:
            selectedChampionStats[soldItemName]["sellerCount"] += 1
        for builtItemName in player["itemsBuilt"]:
            selectedChampionStats[builtItemName]["builderCount"] += 1
            selectedChampionStats[builtItemName]["buildTimeSum"] += player["itemsBuilt"][builtItemName]["timestamp"]
            if "priorityScore" in player["itemsBuilt"][builtItemName]:
                selectedChampionStats[builtItemName]["priorityScoreSum"] += player["itemsBuilt"][builtItemName]["priorityScore"]

def processMatchDataFile(statsDict, matchVersion, matchType, matchRegion):
    typeFolder = {"normal":"NORMAL_5X5", "ranked":"RANKED_SOLO"}[matchType]
    jsonPath = "dataset/" + matchVersion + "/" + typeFolder + "/" + matchRegion + ".json"
    logging.debug("Starting threaded work for " + jsonPath)
    regionMatchList = json.load(io.open(jsonPath))
    regionKey = matchRegion.lower()

    counter = 1
    for matchId in regionMatchList:
        putStats(statsDict, matchId, matchVersion, matchType, regionKey)
        if counter % 100 == 0:
            logging.debug("[" + matchVersion + "/" + matchType + "/" + regionKey + "] " + str(counter) + " matches read. (" + str(100.0*counter/len(regionMatchList)) + "%)")
        counter += 1

    writePath = "stats/" + matchVersion + "_" + matchType + "_" + regionKey + ".json"

    # Write stats to a json file
    logging.debug("[" + matchVersion + "/" + matchType + "/" + regionKey + "] Writing " + writePath + ".")
    stream = open(writePath, 'w')
    json.dump(statsDict, stream)
    stream.close()
    logging.debug("[" + matchVersion + "/" + matchType + "/" + regionKey + "] Work complete!")

STATS_TEMPLATE = {"5.11":{"normal":{}, "ranked":{}}, "5.14":{"normal":{}, "ranked":{}}}

itemStructure = {"mageCount":0, "totalCount":0}
for itemName in AP_ITEM_NAMES:
    itemStructure[itemName] = {"builderCount":0, "sellerCount":0, "buildTimeSum":0, "priorityScoreSum":0}
for champKey in CHAMP_DATA.keys():
    name = CHAMP_DATA[champKey]["name"]
    STATS_TEMPLATE["5.11"]["normal"][name] = copy.deepcopy(itemStructure)
    STATS_TEMPLATE["5.11"]["ranked"][name] = copy.deepcopy(itemStructure)
    STATS_TEMPLATE["5.14"]["normal"][name] = copy.deepcopy(itemStructure)
    STATS_TEMPLATE["5.14"]["ranked"][name] = copy.deepcopy(itemStructure)

# There are 4 folders: dataset/5.11/NORMAL_5X5, dataset/5.11/RANKED_SOLO, dataset/5.14/NORMAL_5X5, and dataset/5.14/RANKED_SOLO.
# For safety, we'll run each server separately.
PARAMETERS = [{"version":"5.11", "type":"normal", "typeFolder":"NORMAL_5X5"},
                   {"version":"5.11", "type":"ranked", "typeFolder":"RANKED_SOLO"},
                   {"version":"5.14", "type":"normal", "typeFolder":"NORMAL_5X5"},
                   {"version":"5.14", "type":"ranked", "typeFolder":"RANKED_SOLO"}]
REGIONS = ["BR",
           "EUNE",
           "EUW",
           "KR",
           "LAN",
           "LAS",
           "NA",
           "OCE",
           "RU",
           "TR"]

for parameters in PARAMETERS:
    for region in REGIONS:
        thread = threading.Thread(target=processMatchDataFile, args=(copy.deepcopy(STATS_TEMPLATE), parameters["version"], parameters["type"], region,))
        thread.start()
