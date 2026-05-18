// Matches the backend TRADITIONS config.
// Each entry includes display metadata and church info for the About section.
// Ordering: Eastern Orthodox by canonical diptychs order, then Oriental Orthodox
// by founding date, then Church of the East.
export const TRADITIONS = {
  // ── Eastern Orthodox (Chalcedonian) — canonical diptychs order ─────────────
  greek: {
    label: "Ecumenical Patriarchate", calendar: "Revised",
    website: "https://www.patriarchate.org",
    founded: "c. 36 AD (traditional)",
    patron: "Saint Andrew the Apostle",
    description: "The Ecumenical Patriarchate of Constantinople holds the primacy of honor in the Orthodox Church and serves as its spiritual center. Founded by the Apostle Andrew, it remains the seat of the first hierarch of Orthodoxy despite the Ottoman conquest of 1453.",
    logo: "☩",
  },
  alexandria: {
    label: "Alexandrian", calendar: "Revised",
    website: "https://www.patriarchateofalexandria.com",
    founded: "42 AD",
    patron: "Saint Mark the Evangelist",
    description: "The Greek Orthodox Patriarchate of Alexandria and All Africa, founded by the Evangelist Mark in 42 AD. The Catechetical School of Alexandria — home to Clement, Origen, and Athanasius — shaped Christian theology for centuries. The Patriarchate today serves across the African continent.",
    logo: "☩",
  },
  antioch: {
    label: "Antiochian", calendar: "Revised",
    website: "https://antiochpatriarchate.org",
    founded: "37 AD",
    patron: "Saints Peter and Paul",
    description: "The Greek Orthodox Patriarchate of Antioch and All the East — where believers were first called Christians (Acts 11:26). Founded by Saints Peter and Paul, it is one of the ancient Pentarchy and serves communities across the Middle East and its diaspora, with liturgy in Arabic.",
    logo: "☩",
  },
  jerusalem: {
    label: "Jerusalem", calendar: "Julian",
    website: "https://www.jerusalem-patriarchate.info",
    founded: "33 AD (Pentecost)",
    patron: "Saint James the Brother of the Lord",
    description: "The Greek Orthodox Patriarchate of Jerusalem — the most ancient of all Christian communities, established at Pentecost in 33 AD. Custodian of the holiest Christian sites: the Church of the Holy Sepulchre, the Garden of Gethsemane, Bethlehem, and Nazareth.",
    logo: "✚",
  },
  russian: {
    label: "Russian", calendar: "Julian",
    website: "https://www.patriarchia.ru",
    founded: "988 AD (Patriarchate 1589)",
    patron: "Equal-to-Apostles Vladimir",
    description: "The Russian Orthodox Church (Moscow Patriarchate). Christianity came to Rus in 988 under Prince Vladimir. The Moscow Patriarchate received autocephaly in 1448 and was elevated to a Patriarchate in 1589. The largest Orthodox church by number of faithful worldwide.",
    logo: "☦",
  },
  georgian: {
    label: "Georgian", calendar: "Julian",
    website: "https://www.patriarchate.ge",
    founded: "337 AD",
    patron: "Saint Nino, Equal-to-Apostles",
    description: "The Apostolic Autocephalous Orthodox Church of Georgia — one of the world's oldest Christian nations. Saint Nino brought the faith to Georgia circa 327 AD. The Church developed its own unique script for biblical translation and preserved Georgian identity through centuries of invasion.",
    logo: "✠",
  },
  serbian: {
    label: "Serbian", calendar: "Julian",
    website: "https://www.spc.rs",
    founded: "1219 AD",
    patron: "Saint Sava",
    description: "The Serbian Orthodox Church, granted autocephaly in 1219 by the Ecumenical Patriarchate through Saint Sava, first Serbian Archbishop. Maintains the full Byzantine liturgical tradition on the Julian calendar. Headquartered in Belgrade.",
    logo: "☩",
  },
  romanian: {
    label: "Romanian", calendar: "Revised",
    website: "https://patriarhia.ro",
    founded: "1st century (tradition), Patriarchate 1925",
    patron: "Saint Andrew the Apostle",
    description: "The Romanian Orthodox Church, one of the largest Orthodox churches with approximately 19 million faithful. Its apostolic heritage traces to Saint Andrew who preached in Scythia Minor (today's Dobrogea). The Patriarchate plays a central role in the cultural life of Romania and its diaspora.",
    logo: "☦",
  },
  bulgarian: {
    label: "Bulgarian", calendar: "Revised",
    website: "https://bg-patriarshia.bg",
    founded: "870 AD (Patriarchate 927)",
    patron: "Saints Cyril and Methodius",
    description: "The Bulgarian Orthodox Church (Bulgarian Patriarchate), established in 927, was the first Slavic Patriarchate. Disciples of Saints Cyril and Methodius created the Glagolitic and Cyrillic alphabets here, enabling Christian literacy throughout the Slavic world.",
    logo: "☦",
  },
  cyprus: {
    label: "Cyprus", calendar: "Revised",
    website: "https://www.churchofcyprus.org.cy",
    founded: "45 AD (traditional), Autocephalous 431 AD",
    patron: "Saint Barnabas the Apostle",
    description: "The Church of Cyprus, one of the oldest autocephalous Orthodox churches, was declared self-governing at the Council of Ephesus in 431 AD. Saint Barnabas, companion of Paul, founded the church on Cyprus (Acts 13). The Archbishop of Cyprus holds the ancient Byzantine privilege of signing in red ink.",
    logo: "☩",
  },
  // ── Oriental Orthodox (Non-Chalcedonian) — by founding date ────────────────
  syriac: {
    label: "Syriac Orthodox", calendar: "Julian", note: "Non-Chalcedonian",
    website: "https://syriacpatriarchate.org",
    founded: "37 AD (traditional)",
    patron: "Saints Peter, Paul, and Ignatius of Antioch",
    description: "The Syriac Orthodox Church of Antioch traces its roots to the Apostolic See of Antioch (c. 37 AD). Separated from the Chalcedonian church in 451 AD, it preserves Syriac — a dialect of Aramaic, the language of Christ — as its liturgical language. The Patriarch of Antioch and All the East is headquartered in Damascus.",
    logo: "✠",
  },
  coptic: {
    label: "Coptic", calendar: "Coptic", note: "Non-Chalcedonian",
    website: "https://www.copticchurch.net",
    founded: "42 AD",
    patron: "Saint Mark the Evangelist",
    description: "The Coptic Orthodox Church of Alexandria, founded by Saint Mark the Evangelist in 42 AD. Separated from Chalcedonian communion in 451 AD on Christological grounds, the Coptic Church preserves an unbroken apostolic tradition and gave monasticism to the world through Saints Anthony and Pachomius.",
    logo: "☩",
  },
  malankara: {
    label: "Malankara", calendar: "Gregorian", note: "Non-Chalcedonian",
    website: "https://www.mosc.in",
    founded: "52 AD (traditional, Saint Thomas)",
    patron: "Saint Thomas the Apostle",
    description: "The Malankara Orthodox Syrian Church traces its foundation to the Apostle Thomas, who arrived in Kerala, India in 52 AD. India's oldest Christian community, it uses the West Syriac (Antiochene) rite enriched with Kerala traditions and has been in full Oriental Orthodox communion with the Syriac Patriarchate of Antioch since the 20th century.",
    logo: "✙",
  },
  armenian: {
    label: "Armenian Apostolic", calendar: "Gregorian", note: "Non-Chalcedonian",
    website: "https://www.armenianchurch.us",
    founded: "301 AD",
    patron: "Saint Gregory the Illuminator",
    description: "The Armenian Apostolic Church — Armenia was the first nation to adopt Christianity as state religion in 301 AD under King Tiridates III and Saint Gregory the Illuminator. The Church uniquely celebrates the Nativity on January 6 (Epiphany) without a separate December feast.",
    logo: "✙",
  },
  ethiopian: {
    label: "Ethiopian", calendar: "Ethiopian", note: "Non-Chalcedonian",
    website: "https://www.ethiopianorthodox.org",
    founded: "340 AD",
    patron: "Saint Frumentius (Abba Selama)",
    description: "The Ethiopian Orthodox Tewahedo Church — one of the oldest Christian churches. Ethiopia received Christianity circa 340 AD through Saints Frumentius and Aedesius. The Tewahedo ('unified') Church preserves the Book of Enoch, the Book of Jubilees, and other ancient texts absent from Western canons.",
    logo: "✙",
  },
  // ── Church of the East ──────────────────────────────────────────────────────
  assyrian: {
    label: "Assyrian", calendar: "Gregorian", note: "Church of the East",
    website: "https://www.assyrianchurch.org",
    founded: "1st century AD (Apostolic)",
    patron: "Saints Thomas, Addai, and Mari",
    description: "The Assyrian Church of the East — one of Christianity's oldest institutions, tracing its origins to the apostolic mission of Saints Thomas, Addai, and Mari in Mesopotamia. Independent of both Chalcedonian and non-Chalcedonian councils, it preserves the ancient East Syriac liturgical tradition, including the Anaphora of Addai and Mari, one of the oldest Eucharistic prayers in existence.",
    logo: "✝",
  },
};

// ── World Orthodox Directory ──────────────────────────────────────────────────
// Canonical, recognized churches only. No self-proclaimed bodies.
// Symbols: ☦ Eastern Orthodox (Chalcedonian)  ✙ Oriental Orthodox  ✝ Church of the East
export const WORLD_CHURCHES = [
  {
    category: "Eastern Orthodox",
    subtitle: "Chalcedonian",
    symbol: "☦",
    churches: [
      // Autocephalous — canonical diptychs order
      { name: "Ecumenical Patriarchate of Constantinople",   url: "https://www.patriarchate.org" },
      { name: "Greek Orthodox Patriarchate of Alexandria",   url: "https://www.patriarchateofalexandria.com" },
      { name: "Greek Orthodox Patriarchate of Antioch",      url: "https://antiochpatriarchate.org" },
      { name: "Greek Orthodox Patriarchate of Jerusalem",    url: "https://www.jerusalem-patriarchate.info" },
      { name: "Russian Orthodox Church",                     url: "https://www.patriarchia.ru" },
      { name: "Georgian Orthodox Church",                    url: "https://www.patriarchate.ge" },
      { name: "Serbian Orthodox Church",                     url: "https://www.spc.rs" },
      { name: "Romanian Orthodox Church",                    url: "https://patriarhia.ro" },
      { name: "Bulgarian Orthodox Church",                   url: "https://bg-patriarshia.bg" },
      { name: "Church of Cyprus",                            url: "https://www.churchofcyprus.org.cy" },
      { name: "Church of Greece",                            url: "https://www.ecclesia.gr" },
      { name: "Polish Orthodox Church",                      url: "https://www.orthodox.pl" },
      { name: "Albanian Orthodox Church",                    url: "https://orthodoxalbania.org" },
      { name: "Czech and Slovak Orthodox Church",            url: "https://www.pravoslavnacirkev.cz" },
      { name: "Orthodox Church in America",                  url: "https://www.oca.org" },
      { name: "Orthodox Church of Ukraine",                  url: "https://www.pcu.ua" },
      { name: "Ukrainian Orthodox Church",                   url: "https://church.ua" },
      { name: "Orthodox Ohrid Archdiocese",                  url: "https://www.ohridarchdiocese.org" },
      // Autonomous
      { name: "Finnish Orthodox Church",                     url: "https://www.ort.fi" },
      { name: "Estonian Apostolic Orthodox Church",          url: "https://www.eaoc.ee" },
      { name: "Japanese Orthodox Church",                    url: "https://www.orthodoxjapan.jp" },
    ],
  },
  {
    category: "Oriental Orthodox",
    subtitle: "Non-Chalcedonian",
    symbol: "✙",
    churches: [
      { name: "Coptic Orthodox Church of Alexandria",        url: "https://www.copticchurch.net" },
      { name: "Syriac Orthodox Church of Antioch",           url: "https://syriacpatriarchate.org" },
      { name: "Armenian Apostolic Church — Etchmiadzin",     url: "https://www.armenianchurch.am" },
      { name: "Armenian Apostolic Church — Cilicia",         url: "https://www.catholicateofcilicia.org" },
      { name: "Armenian Patriarchate of Constantinople",     url: "https://www.armenianpatriarchate.org.tr" },
      { name: "Armenian Patriarchate of Jerusalem",          url: "https://armenian-patriarchate.com" },
      { name: "Ethiopian Orthodox Tewahedo Church",          url: "https://www.ethiopianorthodox.org" },
      { name: "Eritrean Orthodox Tewahedo Church",           url: "https://eritreanorthodox.net" },
      { name: "Malankara Orthodox Syrian Church",            url: "https://www.mosc.in" },
    ],
  },
  {
    category: "Church of the East",
    subtitle: "East Syriac tradition",
    symbol: "✝",
    churches: [
      { name: "Assyrian Church of the East",                 url: "https://www.assyrianchurch.org" },
      { name: "Ancient Church of the East",                  url: "https://ancientchurchoftheeast.org" },
    ],
  },
];
