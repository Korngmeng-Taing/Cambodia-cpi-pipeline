"""
scripts/build_5digit_weights_seed.py
Maps CEIC Phnom Penh CPI weights to hierarchical UN COICOP structure:
Division -> Group -> Class -> Subclass
"""
import csv
import json
from pathlib import Path

CEIC_JSON = Path(r"D:\CPI PIPELINE\ceic_extracted_weights.json")
OUTPUT_CSV = Path(r"D:\CPI PIPELINE\dbt\seeds\cambodia_cpi_coicop_weights_breakdown.csv")

with open(CEIC_JSON, "r", encoding="utf-8") as f:
    items = json.load(f)

ceic_map = {x["title"]: x["weight"] for x in items}

# Structure mapping with Khmer translations
# Each tuple: (level, code, name_en, name_kh, parent_div, weight_key_or_float)
COICOP_HIERARCHY = [
    # --- Division 01: Food and Non-Alcoholic Beverages ---
    ("Division", "01", "Food and non-alcoholic beverages", "ម្ហូបអាហារ និងភេសជ្ជៈមិនមែនជាតិស្រវឹង", "01", "Food & Non Alcoholic Beverage (FB)"),
    ("Group", "01.1", "Food", "ម្ហូបអាហារ", "01", "FB: Food"),
    
    # Class 01.1.1: Bread & Cereals
    ("Class", "01.1.1", "Bread and cereals", "អង្ករ មី នំប៉័ង ម្សៅ", "01", "FB: Food: Bread & Cereals (BC)"),
    ("Subclass", "01.1.1.1", "Rice", "អង្ករ", "01", "FB: Food: BC: Rice"),
    ("Subclass", "01.1.1.1.1", "Rice: Quality 1 (Jasmine / Phka Rumduol)", "អង្ករផ្ការំដួល/ម្លិះ លេខ១", "01", "FB: Food: BC: Rice: Quality 1"),
    ("Subclass", "01.1.1.1.2", "Rice: Quality 2 (Mixed White Rice)", "អង្ករសចម្រុះ លេខ២", "01", "FB: Food: BC: Rice: Quality 2"),
    ("Subclass", "01.1.1.1.3", "Rice: Glutinous (Sticky Rice)", "អង្ករដំណើប លេខ១", "01", "FB: Food: BC: Rice: Glutinous Quality 1"),
    ("Subclass", "01.1.1.2", "Bread (French Baguette / Sandwich)", "នំប៉័ង", "01", "FB: Food: BC: Bread"),
    ("Subclass", "01.1.1.3", "Noodles and pasta", "មី និងគុយទាវ", "01", "FB: Food: BC: Noodles"),
    ("Subclass", "01.1.1.4", "Biscuits and crackers", "នំស្រួយ និងប៊ីសស្គី", "01", "FB: Food: BC: Biscuit"),
    ("Subclass", "01.1.1.5", "Traditional cakes and pastries", "នំខ្មែរបុរាណ និងនំផ្អែម", "01", "FB: Food: BC: Traditional Cake"),
    ("Subclass", "01.1.1.9", "Other cereals and flour", "ម្សៅ និងគ្រាប់ធញ្ញជាតិផ្សេងៗ", "01", "FB: Food: BC: Other Grains"),

    # Class 01.1.2: Meat
    ("Class", "01.1.2", "Meat", "សាច់", "01", "FB: Food: Meat"),
    ("Subclass", "01.1.2.1", "Fresh pork", "សាច់ជ្រូកស្រស់", "01", "FB: Food: Meat: Fresh Pork"),
    ("Subclass", "01.1.2.2", "Fresh beef", "សាច់គោស្រស់", "01", "FB: Food: Meat: Fresh Beef"),
    ("Subclass", "01.1.2.3", "Fresh chicken", "សាច់មាន់ស្រស់", "01", "FB: Food: Meat: Fresh Chicken"),
    ("Subclass", "01.1.2.4", "Fresh duck", "សាច់ទាស្រស់", "01", "FB: Food: Meat: Fresh Duck"),
    ("Subclass", "01.1.2.5", "Locally processed meat (Pork sausage, paté)", "សាច់កែច្នៃ សាច់ក្រក ប៉ាតេ", "01", "FB: Food: Meat: Locally Processed Meat"),

    # Class 01.1.3: Fish and Seafood
    ("Class", "01.1.3", "Fish and seafood", "ត្រី និងគ្រឿងសមុទ្រ", "01", "FB: Food: Fish & Seafood (FS)"),
    ("Subclass", "01.1.3.1", "Fresh fish (Freshwater & marine)", "ត្រីស្រស់ (ត្រីរ៉ស់ ត្រីប្រា ត្រីឆ្តោ)", "01", "FB: Food: FS: Fresh Fish"),
    ("Subclass", "01.1.3.2", "Seafood (Fresh shrimp, crab, squid)", "គ្រឿងសមុទ្រស្រស់ (បង្គា ក្តាម មឹក)", "01", "FB: Food: FS: Seafood"),
    ("Subclass", "01.1.3.3", "Processed fish and seafood (Prahok, dried fish, canned)", "ត្រីកែច្នៃ ប្រហុក ត្រីងៀត ត្រីខ", "01", "FB: Food: FS: Processed Fish & Seafood"),

    # Class 01.1.4: Milk, Cheese and Eggs
    ("Class", "01.1.4", "Milk, cheese and eggs", "ទឹកដោះគោ ឈីស និងស៊ុត", "01", "FB: Food: Milk, Cheese & Egg (ME)"),
    ("Subclass", "01.1.4.1", "Fresh eggs (Chicken and duck eggs)", "ពងមាន់ ពងទាស្រស់", "01", "FB: Food: ME: Fresh Egg"),
    ("Subclass", "01.1.4.2", "Processed eggs (Salted & century eggs)", "ពងទាប្រៃ ពងទាកូន", "01", "FB: Food: ME: Processed Egg"),
    ("Subclass", "01.1.4.3", "Dairy products (Condensed milk, fresh milk)", "ទឹកដោះគោខាប់ ទឹកដោះគោស្រស់", "01", "FB: Food: ME: Dairy Product"),

    # Class 01.1.5: Oils and Fats
    ("Class", "01.1.5", "Oils and fats", "ប្រេងឆា និងខ្លាញ់", "01", "FB: Food: Oil & Fat"),

    # Class 01.1.6: Fruit
    ("Class", "01.1.6", "Fruit", "ផ្លែឈើ", "01", "FB: Food: Fruit"),
    ("Subclass", "01.1.6.1", "Fresh fruit (Bananas, mangoes, oranges)", "ផ្លែឈើស្រស់ ចេក ស្វាយ ក្រូច", "01", "FB: Food: Fruit: Fresh Fruit"),
    ("Subclass", "01.1.6.2", "Dried nuts and edible seeds", "គ្រាប់ធញ្ញជាតិ និងគ្រាប់ផ្លែឈើស្ងួត", "01", "FB: Food: Fruit: Dried Nuts & Edible Seeds"),
    ("Subclass", "01.1.6.3", "Dried and preserved fruit", "ផ្លែឈើដំណាប់ និងកែច្នៃ", "01", "FB: Food: Fruit: Dried & Preserved"),

    # Class 01.1.7: Vegetables
    ("Class", "01.1.7", "Vegetables", "បន្លែ", "01", "FB: Food: Vegetable"),
    ("Subclass", "01.1.7.1", "Leaf and stalk vegetables (Morning glory, cabbage)", "បន្លែស្លឹក ត្រកួន ស្ពៃក្តោប", "01", "FB: Food: Vegetable: Leaf & Stalk"),
    ("Subclass", "01.1.7.2", "Fruit vegetables (Tomatoes, cucumbers, chili)", "បន្លែផ្លែ ប៉េងប៉ោះ ត្រសក់ ម្ទេស", "01", "FB: Food: Vegetable: Fruit Vegetable"),
    ("Subclass", "01.1.7.3", "Root vegetables (Carrots, onions, garlic)", "បន្លែមើម ការ៉ុត ខ្ទឹមបារាំង ខ្ទឹមស", "01", "FB: Food: Vegetable: Root Vegetable"),
    ("Subclass", "01.1.7.4", "Tubers and mushrooms (Potatoes, cassava, mushrooms)", "ដំឡូងបារាំង ដំឡូងមី ផ្សិត", "01", "FB: Food: Vegetable: Tubers & Mushrooms"),
    ("Subclass", "01.1.7.5", "Pulses and legumes (Soybeans, long beans)", "សណ្ដែកកួរ សណ្ដែកសៀង", "01", "FB: Food: Vegetable: Pluses, Legumes"),
    ("Subclass", "01.1.7.6", "Preserved and prepared vegetables (Pickles)", "បន្លែត្រាំ ជ្រក់", "01", "FB: Food: Vegetable: Preserved & Prepared Veg"),

    # Class 01.1.8 & 01.1.9
    ("Class", "01.1.8", "Sugar, jam, honey, chocolate and confectionery", "ស្ករស ទឹកឃ្មុំ សូកូឡា និងស្ករគ្រាប់", "01", "FB: Food: Sugar ,Jam, Honey, Choco & Confection"),
    ("Class", "01.1.9", "Food products n.e.c. (Salt, fish sauce, spices)", "អំបិល ទឹកត្រី ទឹកស៊ីអ៊ីវ គ្រឿងទេស", "01", "FB: Food: Other Food Product, nec"),

    # Group 01.2: Non-alcoholic beverages
    ("Group", "01.2", "Non-alcoholic beverages", "ភេសជ្ជៈមិនមែនជាតិស្រវឹង", "01", "FB: Beverage: Non Alcoholic"),
    ("Class", "01.2.1", "Coffee, tea and cocoa", "កាហ្វេ តែ និងកាកាវ", "01", "FB: Beverage: Non Alcoholic: Coffee, Tea & Cocoa"),
    ("Class", "01.2.2", "Mineral waters, soft drinks, fruit and vegetable juices", "ទឹកបរិសុទ្ធ ទឹកក្រូច កូកាកូឡា ទឹកផ្លែឈើ", "01", "FB: Beverage: Non Alcoholic: Soft Drink: Juice"),

    # --- Division 02: Alcoholic Beverages, Tobacco & Narcotics ---
    ("Division", "02", "Alcoholic beverages, tobacco and narcotics", "ភេសជ្ជៈមានជាតិស្រវឹង និងថ្នាំជក់", "02", "Alcoholic Beverage, Tobacco & Narcotics (AB)"),
    ("Group", "02.1", "Alcoholic beverages", "ភេសជ្ជៈមានជាតិស្រវឹង", "02", "AB: Beverage: Alcoholic"),
    ("Class", "02.1.1", "Spirits and liqueurs (Whisky, brandy, vodka)", "ស្រា ស្រាវីស្គី", "02", "AB: Beverage: Alcoholic: Spirits"),
    ("Class", "02.1.2", "Wine (Red wine, white wine)", "ស្រាក្រហម ស្រាស", "02", "AB: Beverage: Alcoholic: Wine"),
    ("Class", "02.1.3", "Beer (Angkor, Anchor, Cambodia, Heineken)", "ស្រាបៀរ", "02", "AB: Beverage: Alcoholic: Beer"),
    ("Group", "02.2", "Tobacco", "ថ្នាំជក់", "02", "AB: Tobacco"),
    ("Class", "02.2.0", "Tobacco (Cigarettes, cigars)", "បារី ថ្នាំជក់", "02", "AB: Tobacco"),

    # --- Division 03: Clothing and Footwear ---
    ("Division", "03", "Clothing and footwear", "សម្លៀកបំពាក់ និងស្បែកជើង", "03", "Clothing & Footwear (CF)"),
    ("Group", "03.1", "Clothing", "សម្លៀកបំពាក់", "03", "CF: Clothing"),
    ("Class", "03.1.1", "Clothing materials (Fabrics)", "ក្រណាត់កាត់ខោអាវ", "03", "CF: Clothing: Clothing Materials"),
    ("Class", "03.1.2", "Garments", "សម្លៀកបំពាក់សម្រេច", "03", "CF: Clothing: Garments"),
    ("Subclass", "03.1.2.1", "Garments: Women and girls", "សម្លៀកបំពាក់ស្ត្រី និងកុមារី", "03", "CF: Clothing: Garments: Women & Girls"),
    ("Subclass", "03.1.2.2", "Garments: Men and boys", "សម្លៀកបំពាក់បុរស និងកុមារា", "03", "CF: Clothing: Garments: Men & Boys"),
    ("Subclass", "03.1.2.3", "Garments: Infant (< 1 year)", "សម្លៀកបំពាក់ទារក", "03", "CF: Clothing: Garments: Infant: < 1 Yr"),
    ("Subclass", "03.1.2.9", "Other garments", "សម្លៀកបំពាក់ផ្សេងៗ", "03", "CF: Clothing: Garments: Others"),
    ("Class", "03.1.3", "Other articles of clothing and clothing accessories", "គ្រឿងបន្ថែមសម្លៀកបំពាក់", "03", "CF: Clothing: Others & Accessories"),
    ("Class", "03.1.4", "Cleaning, repair and hire of clothing", "ការបោកអ៊ុត និងជួសជុលខោអាវ", "03", "CF: Clothing: Cleaning, Repair & Hire"),
    ("Group", "03.2", "Footwear", "ស្បែកជើង", "03", "CF: Footwear"),
    ("Class", "03.2.1", "Shoes and other footwear", "ស្បែកជើង ស្បែកជើងប៉ាតា ស្បែកជើងផ្ទាត់", "03", "CF: Footwear"),

    # --- Division 04: Housing, Water, Electricity, Gas & Other Fuels ---
    ("Division", "04", "Housing, water, electricity, gas and other fuels", "លំនៅឋាន ទឹក អគ្គិសនី ឧស្ម័ន និងឥន្ធនៈផ្សេងទៀត", "04", "Housing & Utilities (HU)"),
    ("Group", "04.1", "Actual rentals for housing", "ថ្លៃឈ្នួលផ្ទះជាក់ស្តែង", "04", "HU: Housing: Rentals"),
    ("Class", "04.1.1", "Actual rentals paid by tenants", "ថ្លៃឈ្នួលផ្ទះ ឬបន្ទប់ជួល", "04", "HU: Housing: Rentals"),
    ("Group", "04.3", "Maintenance and repair of the dwelling", "ការថែទាំ និងជួសជុលលំនៅឋាន", "04", "HU: Housing: House Maintenance & Repairs (HM)"),
    ("Class", "04.3.1", "Materials for dwelling maintenance and repair", "សម្ភារៈជួសជុលលំនៅឋាន (ស៊ីម៉ង់ត៍ ថ្នាំពណ៌)", "04", "HU: Housing: HM: Materials"),
    ("Class", "04.3.2", "Services for dwelling maintenance and repair", "សេវាជាងសំណង់ និងជួសជុលផ្ទះ", "04", "HU: Housing: HM: Services"),
    ("Group", "04.4", "Water supply and miscellaneous services", "ការផ្គត់ផ្គង់ទឹកស្អាត", "04", "HU: Water Supplies & Miscellaneous Services"),
    ("Class", "04.4.1", "Water supply (Municipal piped tap water)", "ទឹកស្អាតរដ្ឋ", "04", "HU: Water Supplies & Miscellaneous Services"),
    ("Group", "04.5", "Electricity, gas and other fuels", "អគ្គិសនី ហ្គាស និងឥន្ធនៈផ្សេងៗ", "04", "HU: Electricity, Gas & Other Fuel (EG)"),
    ("Class", "04.5.1", "Electricity (EDC grid power)", "អគ្គិសនី អគ្គិសនីកម្ពុជា", "04", "HU: EG: Electricity"),
    ("Class", "04.5.2", "Gas (LPG cooking gas cylinder refill)", "ហ្គាសដាំស្ល", "04", "HU: EG: Gas"),
    ("Class", "04.5.3", "Liquid fuels (Kerosene)", "ប្រេងកាត", "04", "HU: EG: Liquid Fuels"),
    ("Class", "04.5.4", "Solid fuels (Firewood, charcoal)", "ធ្យូង អុស", "04", "HU: EG: Solid Fuels"),

    # --- Division 05: Furnishings & Routine Household Maintenance ---
    ("Division", "05", "Furnishings, household equipment and routine household maintenance", "គ្រឿងសង្ហារឹម ឧបករណ៍ប្រើប្រាស់ក្នុងផ្ទះ និងការថែទាំផ្ទះ", "05", "Furnishing & Household Maintenance (FH)"),
    ("Group", "05.1", "Furniture and furnishings", "គ្រឿងសង្ហារឹម", "05", "FH: Furniture & Carpets"),
    ("Class", "05.1.1", "Furniture and carpets", "តុ កៅអី គ្រែ ពូក កំរាលព្រំ", "05", "FH: Furniture & Carpets"),
    ("Group", "05.2", "Household textiles", "វាយនភណ្ឌប្រើប្រាស់ក្នុងផ្ទះ", "05", "FH: Household Textiles"),
    ("Class", "05.2.1", "Household textiles (Bedsheets, blankets, towels)", "ភួយ កន្សែង កម្រាលពូក", "05", "FH: Household Textiles"),
    ("Group", "05.3", "Household appliances", "ឧបករណ៍ប្រើប្រាស់ក្នុងផ្ទះ", "05", "FH: Household Appliances"),
    ("Class", "05.3.1", "Major and small household appliances (Refrigerators, fans)", "ទូរទឹកកក កង្ហារ អគ្គិសនី", "05", "FH: Household Appliances"),
    ("Group", "05.4", "Glassware, tableware and household utensils", "ចាន កែវ និងសម្ភារៈផ្ទះបាយ", "05", "FH: Glassware & Tableware (GT)"),
    ("Class", "05.4.1", "Glassware and tableware", "ចាន កែវ ឆ្នាំង ខ្ទះ", "05", "FH: Glassware & Tableware (GT)"),
    ("Group", "05.5", "Tools and equipment for house and garden", "ឧបករណ៍ជាង និងសួនច្បារ", "05", "FH: Household Tools & Equipment"),
    ("Class", "05.5.1", "Household tools and equipment", "ញញួរ ដង្កាប់ ទួណឺវិស", "05", "FH: Household Tools & Equipment"),
    ("Group", "05.6", "Goods and services for routine household maintenance", "ទំនិញ និងសេវាកម្មសម្រាប់ថែទាំផ្ទះ", "05", "FH: Household Maintenance"),
    ("Class", "05.6.1", "Non-durable household goods (Detergents, cleaners, soaps)", "សាប៊ូបោកខោអាវ ទឹកលាងចាន ទឹកជូតឥដ្ឋ", "05", "FH: Household Maintenance"),

    # --- Division 06: Health ---
    ("Division", "06", "Health", "សុខាភិបាល", "06", "Health"),
    ("Group", "06.1", "Medical products, appliances and equipment", "ផលិតផល ឧបករណ៍ និងសម្ភារៈវេជ្ជសាស្ត្រ", "06", "Health: Medical Products & Equipments"),
    ("Class", "06.1.1", "Pharmaceutical products (Medicines, painkillers, vitamins)", "ថ្នាំពេទ្យ ប៉ារ៉ាសេតាម៉ុល វីតាមីន", "06", "Health: Medical Products & Equipments"),
    ("Group", "06.2", "Outpatient services", "សេវាអ្នកជំងឺក្រៅ", "06", "Health: Outpatient Services"),
    ("Class", "06.2.1", "Medical services (Doctor consultation, private clinics)", "សេវាពិគ្រោះជំងឺ និងព្យាបាលនៅគ្លីនិក", "06", "Health: Outpatient Services"),
    ("Group", "06.3", "Hospital services", "សេវាមន្ទីរពេទ្យ", "06", "Health: Hospital Services"),
    ("Class", "06.3.1", "Hospital services (Inpatient care)", "សេវាសម្រាកព្យាបាលនៅមន្ទីរពេទ្យ", "06", "Health: Hospital Services"),

    # --- Division 07: Transport ---
    ("Division", "07", "Transport", "ការដឹកជញ្ជូន", "07", "Transportation"),
    ("Group", "07.1", "Purchase of vehicles", "ការទិញមធ្យោបាយធ្វើដំណើរ", "07", "Transportation: Vehicles Purchase (VP)"),
    ("Class", "07.1.1", "Motor cars", "រថយន្តទេសចរណ៍", "07", "Transportation: VP: Motor Cars"),
    ("Class", "07.1.2", "Motorcycles and scooters", "ម៉ូតូ ម៉ូតូស្កូតឺ", "07", "Transportation: VP: Motor Cycles"),
    ("Class", "07.1.3", "Bicycles", "កង់", "07", "Transportation: VP: Bicycles"),
    ("Group", "07.2", "Operation of personal transport equipment", "ប្រតិបត្តិការឧបករណ៍ដឹកជញ្ជូនផ្ទាល់ខ្លួន", "07", "Transportation: Operation Transport Equip (OP)"),
    ("Class", "07.2.1", "Spare parts and accessories for personal transport equipment", "គ្រឿងបន្លាស់ម៉ូតូ និងឡាន (សំបកកង់ អាគុយ)", "07", "Transportation: OP: Spare Parts"),
    ("Class", "07.2.2", "Fuels and lubricants for personal transport equipment", "ប្រេងឥន្ធនៈ និងប្រេងរំអិល", "07", "Transportation: OP: Fuel & Lubricants (FL)"),
    ("Subclass", "07.2.2.1", "Gasoline (Super 95 and Regular)", "ប្រេងសាំង (ស៊ុបពែរ និងធម្មតា)", "07", "Transportation: OP: FL: Gasoline"),
    ("Subclass", "07.2.2.2", "Diesel fuel", "ប្រេងម៉ាស៊ូត", "07", "Transportation: OP: FL: Diesel"),
    ("Subclass", "07.2.2.3", "Motor oil and engine lubricants", "ប្រេងម៉ាស៊ីន និងប្រេងរំអិល", "07", "Transportation: OP: FL: Motor Oil"),
    ("Class", "07.2.3", "Maintenance and repair of personal transport equipment", "ការជួសជុល និងថែទាំយានយន្ត", "07", "Transportation: OP: Maintenance & Repair"),
    ("Group", "07.3", "Transport services", "សេវាដឹកជញ្ជូន", "07", "Transportation: Transport Services"),
    ("Class", "07.3.2", "Passenger transport by bus, taxi, tuk-tuk", "សេវាដឹកអ្នកដំណើរ (ឡានក្រុង តាក់ស៊ី ទុកទុក)", "07", "Transportation: Transport Services"),

    # --- Division 08: Communication ---
    ("Division", "08", "Communication", "ការទំនាក់ទំនង", "08", "Communication"),
    ("Group", "08.2", "Telephone equipment and services", "ឧបករណ៍ និងសេវាទូរស័ព្ទ", "08", "Communication"),
    ("Class", "08.2.0", "Telephone equipment and internet services", "ទូរស័ព្ទដៃ ស៊ីមកាត និងអ៊ីនធឺណិត", "08", "Communication"),

    # --- Division 09: Recreation and Culture ---
    ("Division", "09", "Recreation and culture", "ការកម្សាន្ត និងវប្បធម៌", "09", "Recreation & Culture"),
    ("Group", "09.1", "Audio-visual and photographic equipment", "ឧបករណ៍សំឡេង រូបភាព និងកុំព្យូទ័រ", "09", "Recreation & Culture"),
    ("Class", "09.1.1", "Audio-visual and cultural goods", "ទូរទស្សន៍ ឧបករណ៍កម្សាន្ត និងសៀវភៅ", "09", "Recreation & Culture"),

    # --- Division 10: Education ---
    ("Division", "10", "Education", "ការអប់រំ", "10", "Education"),
    ("Group", "10.1", "Education services", "សេវាអប់រំ", "10", "Education"),
    ("Class", "10.1.0", "Pre-primary to tertiary education (Tuition fees)", "ថ្លៃសិក្សា សាលារៀន សាកលវិទ្យាល័យ", "10", "Education"),

    # --- Division 11: Restaurants and Hotels ---
    ("Division", "11", "Restaurants and hotels", "ភោជនីយដ្ឋាន និងសណ្ឋាគារ", "11", "Restaurants"),
    ("Group", "11.1", "Catering services", "សេវាផ្គត់ផ្គង់ម្ហូបអាហារ", "11", "Restaurants"),
    ("Class", "11.1.1", "Restaurants, cafes and food stalls (Dining out)", "អាហារដ្ឋាន ភោជនីយដ្ឋាន ហាងកាហ្វេ អាហារតាមផ្លូវ", "11", "Restaurants"),

    # --- Division 12: Miscellaneous Goods and Services ---
    ("Division", "12", "Miscellaneous goods and services", "ទំនិញ និងសេវាកម្មផ្សេងៗ", "12", "Miscellaneous Goods & Services (MGS)"),
    ("Group", "12.1", "Personal care", "ការថែទាំផ្ទាល់ខ្លួន", "12", "Miscellaneous Goods & Services (MGS)"),
    ("Class", "12.1.1", "Hairdressing, personal grooming and personal care products", "សាប៊ូកក់សក់ ថ្នាំដុសធ្មេញ គ្រឿងសម្អាង កាត់សក់", "12", "Miscellaneous Goods & Services (MGS)"),

    # --- Summary All Items ---
    ("Summary", "ALL", "All Items (Headline CPI Aggregate Basket)", "ទំនិញទាំងអស់ (សន្ទស្សន៍ថ្លៃទំនិញប្រើប្រាស់សរុប)", "00", 100.000)
]

# Build the CSV output
rows = [["coicop_level", "coicop_code", "coicop_name", "coicop_name_kh", "weight_pct", "parent_division", "source"]]

for level, code, name_en, name_kh, parent_div, weight_key in COICOP_HIERARCHY:
    if isinstance(weight_key, (int, float)):
        weight = float(weight_key)
    elif weight_key in ceic_map:
        weight = float(ceic_map[weight_key])
    else:
        raise ValueError(f"Missing CEIC key: {weight_key}")
    
    rows.append([
        level,
        code,
        name_en,
        name_kh,
        f"{weight:.3f}",
        parent_div,
        "CEIC / NIS Cambodia (Phnom Penh Base: Oct-Dec 2006=100)"
    ])

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerows(rows)

print(f"Successfully generated {len(rows)-1} hierarchical COICOP rows in {OUTPUT_CSV}")
