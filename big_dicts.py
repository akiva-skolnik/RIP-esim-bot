countries_per_id: dict = {
    1: ('poland', 'pl', 'pln'), 2: ('russia', 'ru', 'rub'), 3: ('germany', 'ger', 'dem'),
    4: ('france', 'fr', 'frf'), 5: ('spain', 'es', 'esp'), 6: ('united kingdom', 'gb', 'gbp'),
    7: ('italy', 'it', 'itl'), 8: ('hungary', 'hu', 'huf'), 9: ('romania', 'ro', 'ron'),
    10: ('bulgaria', 'bg', 'bgn'), 11: ('serbia', 'rs', 'rsd'), 12: ('croatia', 'hr', 'hrk'),
    13: ('bosnia and herzegovina', 'ba', 'bam'), 14: ('greece', 'gr', 'grd'),
    15: ('republic of macedonia', 'mk', 'mkd'), 16: ('ukraine', 'ua', 'uah'),
    17: ('sweden', 'se', 'sek'), 18: ('portugal', 'pt', 'pte'), 19: ('lithuania', 'lt', 'ltl'),
    20: ('latvia', 'lv', 'lvl'), 21: ('slovenia', 'si', 'sit'), 22: ('turkey', 'tr', 'try'),
    23: ('brazil', 'br', 'brl'), 24: ('argentina', 'ar', 'ars'), 25: ('mexico', 'mx', 'mxn'),
    26: ('usa', 'us', 'usd'), 27: ('canada', 'ca', 'cad'), 28: ('china', 'cn', 'cny'),
    29: ('indonesia', 'id', 'idr'), 30: ('iran', 'ir', 'irr'), 31: ('south korea', 'kr', 'krw'),
    32: ('taiwan', 'tw', 'twd'), 33: ('israel', 'il', 'nis'), 34: ('india', 'in', 'inr'),
    35: ('australia', 'au', 'aud'), 36: ('netherlands', 'nl', 'nlg'), 37: ('finland', 'fi', 'fim'),
    38: ('ireland', 'i', 'iep'), 39: ('switzerland', 'ch', 'chf'), 40: ('belgium', 'be', 'bef'),
    41: ('pakistan', 'pk', 'pkr'), 42: ('malaysia', 'my', 'myr'), 43: ('norway', 'no', 'nok'),
    44: ('peru', 'pe', 'pen'), 45: ('chile', 'cl', 'clp'), 46: ('colombia', 'co', 'cop'),
    47: ('montenegro', 'me', 'mep'), 48: ('austria', 'a', 'ats'), 49: ('slovakia', 'sk', 'skk'),
    50: ('denmark', 'dk', 'dkk'), 51: ('czech republic', 'cz', 'czk'),
    52: ('belarus', 'by', 'byr'), 53: ('estonia', 'ee', 'eek'), 54: ('philippines', 'ph', 'php'),
    55: ('albania', 'al', 'all'), 56: ('venezuela', 've', 'vef'), 57: ('egypt', 'eg', 'egp'),
    58: ('japan', 'jp', 'jpy'), 59: ('bangladesh', 'bd', 'bdt'), 60: ('vietnam', 'vn', 'vnd'),
    61: ('yemen', 'ye', 'yer'), 62: ('saudi arabia', 'sa', 'sar'), 63: ('thailand', 'th', 'thb'),
    64: ('algeria', 'dz', 'dzd'), 65: ('angola', 'ao', 'aoa'), 66: ('cameroon', 'cm', 'cm'),
    67: ('ivory coast', 'ci', 'ci'), 68: ('ethiopia', 'et', 'etb'), 69: ('ghana', 'gh', 'ghs'),
    70: ('kenya', 'ke', 'kes'), 71: ('libya', 'ly', 'lyd'), 72: ('morocco', 'ma', 'mad'),
    73: ('mozambique', 'mz', 'mzn'), 74: ('nigeria', 'ng', 'ngn'), 75: ('senegal', 'sn', 'sn'),
    76: ('south africa', 'za', 'zar'), 77: ('sudan', 'sd', 'sdg'), 78: ('tanzania', 'tz', 'tzs'),
    79: ('togo', 'tg', 'tg'), 80: ('tunisia', 'tn', 'tnd'), 81: ('uganda', 'ug', 'ugx'),
    82: ('zambia', 'zm', 'zmw'), 83: ('zimbabwe', 'zw', 'zwl'), 84: ('botswana', 'bw', 'bwp'),
    85: ('benin', 'bj', 'bj'), 86: ('burkina faso', 'bf', 'bf'), 87: ('congo', 'cg', 'cg'),
    88: ('central african republic', 'cf', 'cf'), 89: ('dr of the congo', 'cd', 'cdf'),
    90: ('eritrea', 'er', 'ern'), 91: ('gabon', 'ga', 'ga'), 92: ('chad', 'td', 'td'),
    93: ('niger', 'ne', 'ne'), 94: ('mali', 'ml', 'ml'), 95: ('mauritania', 'mr', 'mro'),
    96: ('guinea', 'gn', 'gnf'), 97: ('guinea bissau', 'gw', 'gw'), 98: ('sierra leone', 'sl', 'sll'),
    99: ('liberia', 'lr', 'lrd'), 100: ('equatorial guinea', 'gq', 'gq'), 101: ('namibia', 'na', 'nad'),
    102: ('lesotho', 'ls', 'lsl'), 103: ('swaziland', 'sz', 'szl'), 104: ('madagascar', 'mg', 'mga'),
    105: ('malawi', 'mw', 'mwk'), 106: ('somalia', 'so', 'sos'), 107: ('djibouti', 'dj', 'djf'),
    108: ('rwanda', 'rw', 'rwf'), 109: ('burundi', 'bi', 'bif'),
    110: ('united arab emirates', 'ae', 'aed'), 111: ('syria', 'sy', 'syp'), 112: ('iraq', 'iq', 'iqd'),
    113: ('oman', 'om', 'omr'), 114: ('qatar', 'qa', 'qar'), 115: ('jordan', 'jo', 'jod'),
    116: ('western sahara', 'eh', 'eh'), 117: ('the gambia', 'gm', 'gmd'),
    118: ('south sudan', 'ss', 'ssp'), 119: ('cambodia', 'kh', 'khr'), 120: ('nepal', 'np', 'npr'),
    121: ('bolivia', 'bo', 'bob'), 122: ('ecuador', 'ec', 'ecd'), 123: ('paraguay', 'py', 'pyg'),
    124: ('uruguay', 'uy', 'uyu'), 125: ('honduras', 'hn', 'hnl'),
    126: ('dominican republic', 'do', 'dop'), 127: ('guatemala', 'gt', 'gtq'),
    128: ('kazakhstan', 'kz', 'kzt'), 129: ('sri lanka', 'lk', 'lkr'),
    130: ('afghanistan', 'af', 'afn'), 131: ('armenia', 'am', 'amd'), 132: ('azerbaijan', 'az', 'azn'),
    133: ('georgia', 'ge', 'gel'), 134: ('kyrgyzstan', 'kg', 'kgs'), 135: ('laos', 'la', 'lak'),
    136: ('tajikistan', 'tj', 'tjs'), 137: ('turkmenistan', 'tm', 'tmt'),
    138: ('uzbekistan', 'uz', 'uzs'), 139: ('new zealand', 'nz', 'nzd'), 140: ('guyana', 'gy', 'gyt'),
    141: ('suriname', 'sr', 'srd'), 142: ('nicaragua', 'ni', 'nio'), 143: ('panama', 'pa', 'pab'),
    144: ('costa rica', 'cr', 'crc'), 145: ('mongolia', 'mn', 'mnt'),
    146: ('papua new guinea', 'pg', 'pgk'), 147: ('cuba', 'cu', 'cuc'), 148: ('lebanon', 'lb', 'lbp'),
    149: ('puerto rico', 'pr', 'prd'), 150: ('moldova', 'md', 'mdl'), 151: ('jamaica', 'jm', 'jmd'),
    152: ('el salvador', 'sv', 'svd'), 153: ('haiti', 'ht', 'htg'), 154: ('bahrain', 'bh', 'bhd'),
    155: ('kuwait', 'kw', 'kwd'), 156: ('cyprus', 'cy', 'cy'), 157: ('belize', 'bz', 'bzd'),
    158: ('kosovo', 'xk', 'xkd'), 159: ('east timor', 'tl', 'tld'), 160: ('bahamas', 'bs', 'bsd'),
    161: ('solomon islands', 'sb', 'sbd'), 162: ('myanmar', 'mm', 'mmk'),
    163: ('north korea', 'kp', 'kpw'), 164: ('bhutan', 'bt', 'btn'), 165: ('iceland', 'is', 'isk'),
    166: ('vanuatu', 'vu', 'vut'), 167: ('san marino', 'sm', 'rsm'), 168: ('palestine', 'ps', 'psd'),
    169: ('soviet union', 'su', 'sur'), 170: ('czechoslovakia', 'cshh', 'cs'),
    171: ('yugoslavia', 'yug', 'yug'), 172: ('weimar republic', 'wer', 'wer'),
    173: ('republic of china', 'cn', 'cn'), 174: ('persia', 'prs', 'prs')}


countries_per_server: dict = {
    'luxia': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
              30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
              56, 57, 58, 59, 60, 61, 62, 63, 64, 68, 71, 72, 80, 104, 106, 110, 111, 112, 113, 114, 115, 119, 120, 121,
              122, 123, 124, 125, 126, 127, 128, 130, 131, 132, 133, 134, 135, 136, 137, 138, 140, 141, 142, 143, 144,
              145, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 158, 159, 162, 164, 165],
    'alpha': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
              29, 30, 31, 32, 33, 34, 36, 37, 39, 40, 41, 43, 44, 45, 46, 47, 48, 49, 50, 51, 53, 54, 55, 56, 57, 58,
              60, 64, 71, 72, 80, 121, 131, 132, 133],
    'primera': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
                28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53,
                54, 55, 56, 57, 58, 59, 60, 63, 119, 121, 122, 123, 124, 125, 126, 127, 139, 140, 141, 142, 143, 144,
                147, 149, 150, 151, 152, 153, 156, 157, 158, 160, 165, 167, 168],
    'secura': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
               29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 54, 55, 56,
               57, 58, 60, 63, 119, 120, 121, 122, 123, 124, 125, 126, 127, 130, 135, 140, 141, 142, 143, 144, 145, 146,
               147, 149, 150, 151, 152, 153, 156, 157, 158, 159, 160, 161, 162, 163, 164, 166, 167, 168],
    'suna': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
             29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
             56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82,
             83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107,
             108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128,
             129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149,
             150, 151, 152, 153, 154, 155, 167, 168],
    'epica': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
              30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
              56, 57, 58, 59, 60, 62, 63, 64, 71, 72, 80, 110, 111, 112, 115, 119, 121, 122, 123, 124, 125, 127, 128,
              130, 131, 132, 133, 134, 135, 136, 138, 143, 144, 145, 148, 150, 155, 156, 162, 165],
    'unica': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
              30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
              56, 57, 58, 59, 60, 62, 63, 64, 71, 72, 80, 110, 111, 112, 115, 119, 121, 122, 123, 124, 125, 127, 128,
              130, 131, 132, 133, 134, 135, 136, 138, 143, 144, 145, 148, 150, 155, 156, 162, 165],
    'sigma': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
              30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
              56, 57, 58, 59, 60, 62, 63, 64, 71, 72, 80, 110, 111, 112, 115, 119, 121, 122, 123, 124, 125, 127, 128,
              130, 131, 132, 133, 134, 135, 136, 138, 143, 144, 145, 148, 150, 155, 156, 162, 165]
}
