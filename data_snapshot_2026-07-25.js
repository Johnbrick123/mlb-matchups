// MLB Pitcher/Game matchup data — one row per TEAM's offense vs the opposing pitcher.
// Regenerate this file with update.py (pulls schedule + probables from the MLB StatsAPI).
// Each row's scores are recomputed live in the browser from the raw inputs + weights below,
// so you can tweak the model without re-importing.
window.SLATE = {
  date: "2026-07-25",

  // Scoring model (reverse-engineered from your sheet; edit freely).
  // Each sub-score = clamp( (value - min) / (max - min) * 100 , 0, 100 )
  scales: {
    xERA:    { min: 2.5,   max: 6.5,  higherIsBetter: true },  // facing a worse pitcher = better spot
    bullpen: { min: 2.5,   max: 6.5,  higherIsBetter: true },  // worse opp bullpen = better spot
    ops:     { min: 0.625, max: 0.8,  higherIsBetter: true },
    opsL3:   { min: 0.5,   max: 0.9,  higherIsBetter: true },
    runsL3:  { min: 2,     max: 8,    higherIsBetter: true }
  },
  weights: { xERA: 0.40, ops: 0.30, bullpen: 0.10, runsL3: 0.10, opsL3: 0.10 },

  // One entry per team per game. oppXERA=null means the opposing starter is still TBD.
  rows: [
    { game:"KC @ DET", team:"Kansas City Royals", abbr:"KC",  ha:"Away", pitcher:"Michael Wacha", opp:"Detroit Tigers",        oppPitcher:"Casey Mize",        oppId:663554, oppXERA:3.14, oppBullpenERA:3.82, bullpenSO:57.56, runsL3:4,    ops:0.715, opsL3:0.709 },
    { game:"KC @ DET", team:"Detroit Tigers",       abbr:"DET", ha:"Home", pitcher:"Casey Mize",     opp:"Kansas City Royals",    oppPitcher:"Michael Wacha",     oppId:608379, oppXERA:4.16, oppBullpenERA:5.38, bullpenSO:42.74, runsL3:5,    ops:0.712, opsL3:0.755 },

    { game:"ARI @ WSH", team:"Arizona Diamondbacks", abbr:"ARI", ha:"Away", pitcher:"Mitch Bratt",    opp:"Washington Nationals", oppPitcher:"Foster Griffin",    oppId:656492, oppXERA:3.88, oppBullpenERA:5.09, bullpenSO:37.92, runsL3:7.67, ops:0.704, opsL3:0.994 },
    { game:"ARI @ WSH", team:"Washington Nationals",  abbr:"WSH", ha:"Home", pitcher:"Foster Griffin", opp:"Arizona Diamondbacks", oppPitcher:"Mitch Bratt",       oppId:683352, oppXERA:5.30, oppBullpenERA:4.01, bullpenSO:51.28, runsL3:7.33, ops:0.770, opsL3:0.958 },

    { game:"LAA @ SF", team:"Los Angeles Angels",   abbr:"LAA", ha:"Away", pitcher:"Ryan Johnson",   opp:"San Francisco Giants", oppPitcher:"Robbie Ray",        oppId:592662, oppXERA:4.61, oppBullpenERA:4.42, bullpenSO:43.69, runsL3:2.67, ops:0.702, opsL3:0.675 },
    { game:"LAA @ SF", team:"San Francisco Giants",  abbr:"SF",  ha:"Home", pitcher:"Robbie Ray",     opp:"Los Angeles Angels",   oppPitcher:"Ryan Johnson",      oppId:696270, oppXERA:4.61, oppBullpenERA:4.45, bullpenSO:51.68, runsL3:3,    ops:0.723, opsL3:0.567 },

    { game:"TOR @ BOS", team:"Toronto Blue Jays",   abbr:"TOR", ha:"Away", pitcher:"Dylan Cease",    opp:"Boston Red Sox",       oppPitcher:"Sonny Gray",        oppId:543243, oppXERA:3.63, oppBullpenERA:3.02, bullpenSO:35.51, runsL3:1.67, ops:0.681, opsL3:0.475 },
    { game:"TOR @ BOS", team:"Boston Red Sox",       abbr:"BOS", ha:"Home", pitcher:"Sonny Gray",     opp:"Toronto Blue Jays",    oppPitcher:"Dylan Cease",       oppId:656302, oppXERA:2.93, oppBullpenERA:3.84, bullpenSO:34.93, runsL3:4.33, ops:0.707, opsL3:0.650 },

    { game:"SD @ MIA", team:"San Diego Padres",     abbr:"SD",  ha:"Away", pitcher:"JP Sears",       opp:"Miami Marlins",        oppPitcher:"Eury Pérez",        oppId:691587, oppXERA:4.04, oppBullpenERA:3.79, bullpenSO:36.38, runsL3:5.33, ops:0.690, opsL3:0.931 },
    { game:"SD @ MIA", team:"Miami Marlins",         abbr:"MIA", ha:"Home", pitcher:"Eury Pérez",     opp:"San Diego Padres",     oppPitcher:"JP Sears",          oppId:676664, oppXERA:4.83, oppBullpenERA:3.82, bullpenSO:40.56, runsL3:3.33, ops:0.733, opsL3:0.661 },

    { game:"NYY @ PHI", team:"New York Yankees",    abbr:"NYY", ha:"Away", pitcher:"Ryan Weathers",  opp:"Philadelphia Phillies",oppPitcher:"",                  oppId:null,   oppXERA:null, oppBullpenERA:4.43, bullpenSO:37.68, runsL3:4.33, ops:0.735, opsL3:0.647 },
    { game:"NYY @ PHI", team:"Philadelphia Phillies",abbr:"PHI", ha:"Home", pitcher:"",              opp:"New York Yankees",     oppPitcher:"Ryan Weathers",     oppId:677960, oppXERA:4.55, oppBullpenERA:3.06, bullpenSO:33.00, runsL3:5.33, ops:0.705, opsL3:0.826 },

    { game:"CLE @ TB", team:"Cleveland Guardians",  abbr:"CLE", ha:"Away", pitcher:"Tanner Bibee",   opp:"Tampa Bay Rays",       oppPitcher:"Nick Martinez",     oppId:607259, oppXERA:4.61, oppBullpenERA:4.13, bullpenSO:35.22, runsL3:8,    ops:0.691, opsL3:1.063 },
    { game:"CLE @ TB", team:"Tampa Bay Rays",        abbr:"TB",  ha:"Home", pitcher:"Nick Martinez",  opp:"Cleveland Guardians",  oppPitcher:"Tanner Bibee",      oppId:676440, oppXERA:4.48, oppBullpenERA:3.69, bullpenSO:33.15, runsL3:7.67, ops:0.738, opsL3:0.952 },

    { game:"CHC @ PIT", team:"Chicago Cubs",        abbr:"CHC", ha:"Away", pitcher:"Shota Imanaga",  opp:"Pittsburgh Pirates",   oppPitcher:"Paul Skenes",       oppId:694973, oppXERA:2.75, oppBullpenERA:4.42, bullpenSO:41.03, runsL3:6,    ops:0.751, opsL3:0.806 },
    { game:"CHC @ PIT", team:"Pittsburgh Pirates",   abbr:"PIT", ha:"Home", pitcher:"Paul Skenes",    opp:"Chicago Cubs",         oppPitcher:"Shota Imanaga",     oppId:684007, oppXERA:3.74, oppBullpenERA:4.07, bullpenSO:44.44, runsL3:3.33, ops:0.763, opsL3:0.552 },

    { game:"ATL @ BAL", team:"Atlanta Braves",      abbr:"ATL", ha:"Away", pitcher:"Bryce Elder",    opp:"Baltimore Orioles",    oppPitcher:"Brandon Young",     oppId:687064, oppXERA:4.21, oppBullpenERA:4.09, bullpenSO:33.07, runsL3:4.33, ops:0.734, opsL3:0.705 },
    { game:"ATL @ BAL", team:"Baltimore Orioles",    abbr:"BAL", ha:"Home", pitcher:"Brandon Young",  opp:"Atlanta Braves",       oppPitcher:"Bryce Elder",       oppId:693821, oppXERA:3.85, oppBullpenERA:3.26, bullpenSO:37.20, runsL3:4.33, ops:0.720, opsL3:0.801 },

    { game:"ATH @ MIN", team:"Athletics",           abbr:"ATH", ha:"Away", pitcher:"Mason Barnett",  opp:"Minnesota Twins",      oppPitcher:"",                  oppId:null,   oppXERA:null, oppBullpenERA:5.02, bullpenSO:43.17, runsL3:5,    ops:0.732, opsL3:0.881 },
    { game:"ATH @ MIN", team:"Minnesota Twins",      abbr:"MIN", ha:"Home", pitcher:"",              opp:"Athletics",            oppPitcher:"Mason Barnett",     oppId:686930, oppXERA:5.16, oppBullpenERA:5.60, bullpenSO:54.94, runsL3:5.33, ops:0.734, opsL3:0.706 },

    { game:"HOU @ CHW", team:"Houston Astros",      abbr:"HOU", ha:"Away", pitcher:"Hunter Brown",   opp:"Chicago White Sox",    oppPitcher:"Sean Burke",        oppId:680732, oppXERA:3.56, oppBullpenERA:3.89, bullpenSO:45.41, runsL3:6,    ops:0.728, opsL3:0.879 },
    { game:"HOU @ CHW", team:"Chicago White Sox",    abbr:"CHW", ha:"Home", pitcher:"Sean Burke",     opp:"Houston Astros",       oppPitcher:"Hunter Brown",      oppId:686613, oppXERA:4.01, oppBullpenERA:4.20, bullpenSO:44.35, runsL3:4.67, ops:0.727, opsL3:0.643 },

    { game:"COL @ MIL", team:"Colorado Rockies",    abbr:"COL", ha:"Away", pitcher:"Ryan Feltner",   opp:"Milwaukee Brewers",    oppPitcher:"Robert Gasser",     oppId:688107, oppXERA:3.85, oppBullpenERA:3.53, bullpenSO:42.33, runsL3:3.67, ops:0.745, opsL3:0.679 },
    { game:"COL @ MIL", team:"Milwaukee Brewers",    abbr:"MIL", ha:"Home", pitcher:"Robert Gasser",  opp:"Colorado Rockies",     oppPitcher:"Nolan McLean",      oppId:690997, oppXERA:3.38, oppBullpenERA:4.96, bullpenSO:37.90, runsL3:4,    ops:0.733, opsL3:0.719 },

    { game:"LAD @ NYM", team:"Los Angeles Dodgers", abbr:"LAD", ha:"Away", pitcher:"Yoshinobu Yamamoto", opp:"New York Mets",    oppPitcher:"",                  oppId:null,   oppXERA:null, oppBullpenERA:3.95, bullpenSO:37.29, runsL3:6,    ops:0.773, opsL3:0.792 },
    { game:"LAD @ NYM", team:"New York Mets",        abbr:"NYM", ha:"Home", pitcher:"Nolan McLean",   opp:"Los Angeles Dodgers",  oppPitcher:"Yoshinobu Yamamoto",oppId:808967, oppXERA:3.21, oppBullpenERA:3.77, bullpenSO:35.94, runsL3:3.33, ops:0.687, opsL3:0.725 },

    { game:"CIN @ STL", team:"Cincinnati Reds",     abbr:"CIN", ha:"Away", pitcher:"Hunter Greene",  opp:"St. Louis Cardinals",  oppPitcher:"Andre Pallante",    oppId:669467, oppXERA:3.71, oppBullpenERA:4.21, bullpenSO:59.48, runsL3:3,    ops:0.708, opsL3:0.573 },
    { game:"CIN @ STL", team:"St. Louis Cardinals",  abbr:"STL", ha:"Home", pitcher:"Andre Pallante", opp:"Cincinnati Reds",      oppPitcher:"Hunter Greene",     oppId:668881, oppXERA:4.39, oppBullpenERA:4.77, bullpenSO:50.00, runsL3:1.33, ops:0.700, opsL3:0.408 },

    { game:"SEA @ TEX", team:"Seattle Mariners",    abbr:"SEA", ha:"Away", pitcher:"Bryan Woo",      opp:"Texas Rangers",        oppPitcher:"Nathan Eovaldi",    oppId:543135, oppXERA:4.01, oppBullpenERA:4.26, bullpenSO:38.54, runsL3:4.33, ops:0.686, opsL3:0.697 },
    { game:"SEA @ TEX", team:"Texas Rangers",        abbr:"TEX", ha:"Home", pitcher:"Nathan Eovaldi", opp:"Seattle Mariners",     oppPitcher:"Bryan Woo",         oppId:693433, oppXERA:3.45, oppBullpenERA:3.58, bullpenSO:37.03, runsL3:5,    ops:0.722, opsL3:0.810 }
  ],

  // Reference tables (season / recent form). rpg = runs per game, ops = team OPS.
  runsRank: [
    [1,"Washington",5.5,7.33,8,5.33,5.67,4.24],[2,"Pittsburgh",5.27,3.33,0,5.69,4.87,3.6],[3,"LA Dodgers",5.19,6,9,4.44,5.91,5.01],
    [4,"Chi Cubs",5.1,6,1,5.19,5,4.8],[5,"Milwaukee",5.04,4,4,5.09,4.98,4.87],[6,"Atlanta",4.97,4.33,7,4.98,4.96,4.47],
    [7,"Minnesota",4.81,5.33,10,4.63,4.98,4.19],[8,"Chi Sox",4.78,4.67,4,5,4.58,3.99],[9,"Colorado",4.76,3.67,0,5.04,4.47,3.69],
    [10,"NY Yankees",4.71,4.33,2,4.78,4.64,5.19],[11,"Baltimore",4.58,4.33,5,4.85,4.3,4.18],[12,"Houston",4.55,6,5,4.34,4.76,4.23],
    [13,"Tampa Bay",4.53,7.67,4,4.8,4.27,4.41],[14,"Sacramento",4.49,5,5,4.98,4.12,4.52],[15,"Arizona",4.47,7.67,15,4.65,4.29,4.88],
    [16,"Miami",4.44,3.33,2,4.31,4.56,4.38],[17,"St. Louis",4.44,1.33,1,3.67,5.24,4.25],[18,"Philadelphia",4.35,5.33,5,4.81,3.88,4.78],
    [19,"LA Angels",4.29,2.67,0,3.71,4.88,4.15],[20,"Kansas City",4.25,4,5,4.75,3.72,4.02],[21,"Detroit",4.25,5,5,4.34,4.15,4.63],
    [22,"Boston",4.22,4.33,1,3.86,4.58,4.8],[23,"Cincinnati",4.19,3,5,4.02,4.35,4.42],[24,"Texas",4.19,5,2,4,4.36,4.22],
    [25,"San Diego",4.13,5.33,6,3.69,4.57,4.28],[26,"SF Giants",4.09,3,4,3.83,4.31,4.35],[27,"NY Mets",4.07,3.33,3,4.39,3.78,4.73],
    [28,"Cleveland",4.04,8,6,4.12,3.96,3.96],[29,"Seattle",4.03,4.33,3,4,4.06,4.68],[30,"Toronto",3.94,1.67,2,3.95,3.94,5.02]
  ],
  opsRank: [
    [1,"LA Dodgers",0.773,0.792,1.004,0.735,0.805,0.764],[2,"Washington",0.77,0.958,0.971,0.765,0.775,0.694],[3,"Pittsburgh",0.763,0.552,0.291,0.812,0.716,0.656],
    [4,"Chi Cubs",0.751,0.806,0.44,0.783,0.718,0.748],[5,"Colorado",0.745,0.679,0.513,0.779,0.71,0.679],[6,"Tampa Bay",0.738,0.952,0.642,0.779,0.701,0.714],
    [7,"NY Yankees",0.735,0.647,0.501,0.757,0.716,0.783],[8,"Minnesota",0.734,0.706,0.831,0.73,0.738,0.707],[9,"Atlanta",0.734,0.705,0.889,0.746,0.721,0.72],
    [10,"Miami",0.733,0.661,0.515,0.729,0.736,0.708],[11,"Milwaukee",0.733,0.719,0.758,0.748,0.718,0.729],[12,"Sacramento",0.732,0.881,0.823,0.776,0.7,0.748],
    [13,"Houston",0.728,0.879,0.866,0.713,0.743,0.714],[14,"Chi Sox",0.727,0.643,0.509,0.748,0.708,0.676],[15,"SF Giants",0.723,0.567,0.612,0.704,0.738,0.697],
    [16,"Texas",0.722,0.81,0.526,0.713,0.73,0.683],[17,"Baltimore",0.72,0.801,0.757,0.752,0.686,0.699],[18,"Kansas City",0.715,0.709,0.718,0.757,0.671,0.706],
    [19,"Detroit",0.712,0.755,0.763,0.723,0.702,0.723],[20,"Cincinnati",0.708,0.573,0.699,0.708,0.708,0.703],[21,"Boston",0.707,0.65,0.429,0.695,0.718,0.742],
    [22,"Philadelphia",0.705,0.826,0.682,0.765,0.646,0.756],[23,"Arizona",0.704,0.994,1.506,0.727,0.682,0.757],[24,"LA Angels",0.702,0.675,0.536,0.65,0.753,0.694],
    [25,"St. Louis",0.7,0.408,0.394,0.671,0.728,0.692],[26,"Cleveland",0.691,1.063,0.822,0.717,0.665,0.667],[27,"San Diego",0.69,0.931,0.85,0.653,0.724,0.708],
    [28,"NY Mets",0.687,0.725,0.699,0.698,0.677,0.753],[29,"Seattle",0.686,0.697,0.508,0.688,0.684,0.738],[30,"Toronto",0.681,0.475,0.414,0.694,0.665,0.766]
  ],
  bullpen: [
    ["ATH",5.6,1.51,177,410,43.17],["KC",5.38,1.55,179,311,57.56],["WAS",5.09,1.48,201,392,51.28],["MIN",5.02,1.53,189,344,54.94],
    ["COL",4.96,1.48,160,378,42.33],["CIN",4.77,1.48,207,348,59.48],["LAA",4.45,1.38,180,412,43.69],["PHI",4.43,1.35,132,400,33.00],
    ["PIT",4.42,1.4,184,414,44.44],["SF",4.42,1.41,154,298,51.68],["TEX",4.26,1.32,117,316,37.03],["STL",4.21,1.36,165,330,50.00],
    ["HOU",4.2,1.33,188,414,45.41],["TB",4.13,1.21,123,371,33.15],["BAL",4.09,1.26,125,336,37.20],["CHW",3.89,1.31,200,451,44.35],
    ["NYM",3.95,1.27,156,434,35.94],["DET",3.82,1.33,153,358,42.74],["SD",3.82,1.29,159,437,36.38],["TOR",3.84,1.29,152,428,35.51],
    ["MIA",3.79,1.21,159,392,40.56],["LAD",3.77,1.24,135,362,37.29],["CLE",3.69,1.31,137,389,35.22],["SEA",3.58,1.29,116,301,38.54],
    ["MIL",3.53,1.26,155,409,37.90],["ATL",3.26,1.14,124,375,33.07],["NYY",3.06,1.2,130,345,37.68],["BOS",3.02,1.16,124,355,34.93]
  ]
};
