"""Text of the information pages: About, FAQ, Privacy and Terms.

These are plain, honest drafts. Have a lawyer review Privacy and Terms before you launch,
and have a native Kinyarwanda speaker review every "rw" text.
Each page is a title, an intro and a list of (heading, paragraph) pairs.
"""

PAGES = {
    "about": {
        "en": {
            "title": "About MedFinder Rwanda",
            "intro": "MedFinder Rwanda helps people find out which pharmacies and health facilities have a medicine before they travel.",
            "sections": [
                ("Why we built it", "A trip to a pharmacy or health center is wasted when the medicine is not there. For many families that means lost money, lost time and delayed treatment."),
                ("How it works", "Pharmacy and health center staff enter their stock. You search for a medicine and see who has it, how recently the stock was updated, and how to get there."),
                ("What we do not do", "MedFinder does not sell medicines and does not give medical advice. A status such as In stock does not promise there is enough for every patient, so always confirm with the facility."),
                ("For pharmacies and health centers", "If your facility is listed and you want to report your stock, ask the MedFinder administrator for a staff account."),
            ],
        },
        "rw": {
            "title": "Ibyerekeye MedFinder Rwanda",
            "intro": "MedFinder Rwanda ifasha abantu kumenya farumasi n'ibigo nderabuzima bifite umuti mbere yo gukora urugendo.",
            "sections": [
                ("Impamvu twayikoze", "Urugendo rujya kuri farumasi cyangwa ku kigo nderabuzima ruba impfabusa iyo umuti udahari. Ku miryango myinshi bivuze gutakaza amafaranga n'igihe no gutinda kuvurwa."),
                ("Uko bikora", "Abakozi ba farumasi n'ibigo nderabuzima bandika ububiko bwabo. Ushakisha umuti ukabona ibifite, igihe ububiko buheruka kuvugururwa, n'uko ugerayo."),
                ("Ibyo tudakora", "MedFinder ntigurisha imiti kandi ntitanga inama z'ubuvuzi. Imiterere nka Urahari ntibivuze ko hari uhagije ku barwayi bose, nuko buri gihe banza ubaze ikigo."),
                ("Ku bafarumasiye no ku bigo nderabuzima", "Niba ikigo cyawe kiri ku rutonde kandi ushaka gutanga ububiko bwawe, saba umuyobozi wa MedFinder konti y'umukozi."),
            ],
        },
    },
    "faq": {
        "en": {
            "title": "Frequently asked questions",
            "intro": "Quick answers about using MedFinder Rwanda.",
            "sections": [
                ("Is MedFinder free?", "Yes. Searching and creating an account are free."),
                ("Do I need an account to search?", "No. Anyone can search and use the map. An account only keeps your language and settings."),
                ("How accurate is the stock information?", "Stock is entered by the facility's own staff. If it was not updated in the last 48 hours it is shown as Unverified. Always call the facility before you travel."),
                ("What does In stock mean?", "Staff reported that the medicine is available. It does not promise there is enough for every patient."),
                ("Why is a pharmacy on the map but has no medicines?", "Many facilities are listed from public map data and have not started to report their stock yet."),
                ("I went to a facility and the medicine was not there.", "Press No, it was not on the result. This tells us the stock information was wrong and helps us improve it."),
                ("I forgot my PIN.", "A PIN reset is not available yet. Create a new account with a different phone number, or contact the MedFinder team."),
                ("Can MedFinder tell me which medicine to take?", "No. Ask a pharmacist or doctor. MedFinder only shows where a medicine may be available."),
            ],
        },
        "rw": {
            "title": "Ibibazo bikunze kubazwa",
            "intro": "Ibisubizo bigufi ku bijyanye no gukoresha MedFinder Rwanda.",
            "sections": [
                ("MedFinder ni ubuntu?", "Yego. Gushakisha no gufungura konti ni ubuntu."),
                ("Nkeneye konti kugira ngo mfate ishakisha?", "Oya. Umuntu wese ashobora gushakisha no gukoresha ikarita. Konti ibika ururimi n'igenamiterere ryawe gusa."),
                ("Amakuru y'ububiko ni ukuri kugeza he?", "Ububiko bwandikwa n'abakozi b'ikigo ubwabo. Iyo butavuguruwe mu masaha 48, bugaragara nka Ntibyemejwe. Buri gihe hamagara ikigo mbere yo kugenda."),
                ("Urahari bisobanura iki?", "Abakozi bavuze ko umuti uhari. Ntibivuze ko hari uhagije ku barwayi bose."),
                ("Kuki farumasi iri ku ikarita nta miti ifite?", "Ibigo byinshi byashyizwe ku rutonde bivuye ku makuru y'ikarita rusange kandi ntibiratangira gutanga ububiko bwabyo."),
                ("Najyanye ku kigo umuti ntiwari uhari.", "Kanda Oya, ntawo nabonye ku gisubizo. Bitubwira ko amakuru y'ububiko atari ukuri kandi bidufasha kuyatunganya."),
                ("Nibagiwe PIN yanjye.", "Guhindura PIN ntibirashoboka. Fungura konti nshya ukoresheje indi nimero ya telefone, cyangwa wandikire itsinda rya MedFinder."),
                ("MedFinder ishobora kumbwira umuti nafata?", "Oya. Baza umufarumasiye cyangwa muganga. MedFinder yerekana gusa aho umuti ushobora kuboneka."),
            ],
        },
    },
    "privacy": {
        "en": {
            "title": "Privacy policy",
            "intro": "This page explains what MedFinder Rwanda collects and why. We keep it to the minimum.",
            "sections": [
                ("Searches", "When you search we save the words you typed, the district and the time. We do not save your name, phone number or IP address with a search."),
                ("Your location", "If you press Use my location, your browser sends your approximate position with the search so results can be sorted by distance. We do not store it in our database. Web server logs may record it for a short time."),
                ("Accounts", "If you create an account we store your name, phone number, preferred language and a scrambled (hashed) copy of your PIN. We never store your PIN itself. You can delete your account in Settings, which removes these details."),
                ("Patient feedback", "When you answer Did you go here, we save only the facility, the medicine and your yes or no. It is not linked to you."),
                ("Other services", "Maps are drawn with Leaflet and OpenStreetMap, fonts come from Google Fonts, and the Directions button opens Google Maps. These services can see your IP address when your browser loads them."),
                ("Cookies", "We use one small cookie to keep you signed in and remember your language. We do not use advertising cookies."),
                ("Changes", "If we change this policy we will update this page."),
            ],
        },
        "rw": {
            "title": "Ibanga ry'amakuru",
            "intro": "Uru rupapuro rusobanura amakuru MedFinder Rwanda ikusanya n'impamvu. Tuyagumana ku rugero ruto.",
            "sections": [
                ("Ishakisha", "Iyo ushakisha tubika amagambo wanditse, akarere n'igihe. Ntitubika izina ryawe, nimero ya telefone cyangwa aderesi ya IP hamwe n'ishakisha."),
                ("Aho uri", "Iyo ukanze Koresha aho ndi, urubuga rwawe rwohereza aho uri ku buryo bugereranijwe hamwe n'ishakisha kugira ngo ibisubizo bitondekwe ukurikije intera. Ntitubika aho uri mu bubiko bwacu bw'amakuru. Ibitabo bya seriveri bishobora kubibika igihe gito."),
                ("Konti", "Iyo ufunguye konti tubika izina ryawe, nimero ya telefone, ururimi ukunda n'agahishe (hashed) ka PIN yawe. Ntituzigera tubika PIN ubwayo. Ushobora gusiba konti yawe mu Igenamiterere, bigahanagura ayo makuru."),
                ("Ibisubizo by'abarwayi", "Iyo usubije Warugeze aha, tubika gusa ikigo, umuti na Yego cyangwa Oya yawe. Ntibihuzwa nawe."),
                ("Izindi serivisi", "Amakarita ashushanywa na Leaflet na OpenStreetMap, inyuguti ziva kuri Google Fonts, kandi buto ya Inzira ifungura Google Maps. Izi serivisi zishobora kubona aderesi ya IP yawe iyo urubuga rwawe rubifunguye."),
                ("Cookies", "Dukoresha cookie imwe ntoya kugira ngo ukomeze kuba winjiye kandi twibuke ururimi rwawe. Ntidukoresha cookies z'amamenyekanisha."),
                ("Impinduka", "Nitugira icyo duhindura kuri iyi politiki tuzavugurura uru rupapuro."),
            ],
        },
    },
    "terms": {
        "en": {
            "title": "Terms of use",
            "intro": "By using MedFinder Rwanda you agree to these terms.",
            "sections": [
                ("What MedFinder is", "MedFinder is an information service. It shows stock that pharmacies and health facilities report. It does not sell medicines or provide medical advice."),
                ("Information may be wrong", "Stock changes quickly. Information can be out of date or incorrect. Always confirm with the facility before you travel. We do not promise that a medicine will be available."),
                ("Medical decisions", "Do not use MedFinder to decide which medicine to take. Ask a pharmacist or doctor. In an emergency go to the nearest health facility or call the emergency number."),
                ("Your account", "Keep your PIN private. You are responsible for what happens under your account. Give correct details when you register."),
                ("Facility staff", "Staff who report stock must keep it accurate and up to date. Accounts can be suspended if stock is reported falsely."),
                ("Acceptable use", "Do not try to break, overload or misuse the service, and do not enter false information."),
                ("Liability", "To the extent the law allows, MedFinder Rwanda is not responsible for losses that come from relying on the information shown."),
                ("Changes", "We may update these terms. Continuing to use MedFinder means you accept the updated terms."),
            ],
        },
        "rw": {
            "title": "Amabwiriza yo gukoresha",
            "intro": "Ukoresheje MedFinder Rwanda uba wemeye aya mabwiriza.",
            "sections": [
                ("MedFinder ni iki", "MedFinder ni serivisi itanga amakuru. Yerekana ububiko bwatanzwe na farumasi n'ibigo nderabuzima. Ntigurisha imiti kandi ntitanga inama z'ubuvuzi."),
                ("Amakuru ashobora kuba atari yo", "Ububiko buhinduka vuba. Amakuru ashobora kuba yarashaje cyangwa atari yo. Buri gihe baza ikigo mbere yo kugenda. Ntitwemeza ko umuti uzaboneka."),
                ("Ibyemezo by'ubuvuzi", "Ntukoreshe MedFinder wihitiramo umuti wafata. Baza umufarumasiye cyangwa muganga. Mu gihe cy'ubutabazi jya ku kigo nderabuzima kikwegereye cyangwa uhamagare nimero y'ubutabazi."),
                ("Konti yawe", "Ika PIN yawe ibanga. Ni wowe ubazwa ibikozwe kuri konti yawe. Tanga amakuru nyayo wiyandikisha."),
                ("Abakozi b'ibigo", "Abakozi batanga ububiko bagomba kubugumisha ari ukuri kandi bugezweho. Konti zishobora guhagarikwa iyo ububiko butanzwe ibinyoma."),
                ("Imikoreshereze yemewe", "Ntugerageze kwangiza, kurenza ubushobozi cyangwa gukoresha nabi iyi serivisi, kandi ntushyiremo amakuru y'ibinyoma."),
                ("Inshingano", "Ku rugero amategeko yemera, MedFinder Rwanda ntiryozwa igihombo giturutse ku kwishingikiriza ku makuru yerekanwa."),
                ("Impinduka", "Dushobora kuvugurura aya mabwiriza. Gukomeza gukoresha MedFinder bivuze ko wemeye amabwiriza avuguruye."),
            ],
        },
    },
}