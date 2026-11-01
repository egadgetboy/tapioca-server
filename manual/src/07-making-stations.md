# Making Stations

There are four ways to make a Station, all on the **Stations** tab:

- **New station:** one Station, with titles you pick or a filter.
- **Smart stations:** up to 50 at once from a filter, one, or one for each decade, genre, studio and more.
- **From Plex collections:** one for each collection you pick, up to 200 at once.
- **Duplicate,** on a Station's card: a copy to change before saving.

## Making a Station

1. Choose **New station**.
2. Give it a **Number** (1 to 9999) and a **Name** (up to 60 characters). With no name, it's called "Station 12", after its number.
3. Choose a **Logo** (see Station features).
4. Under **What's on this station**, choose **Pick shows & movies** or **Use a filter**.
5. Change anything under **How it plays**, **Specials**, **Between programs**, **On screen** and **When someone tunes in**. Each group shows a summary when closed.
6. Choose **Save station**.

A new Station starts with the settings chosen in the setup's **New station settings** step (see the Settings reference for each default). If you close the editor with unsaved changes, it asks first.

[[screenshot: The Station editor, with Pick shows & movies chosen and posters to pick from]]

### Picking shows and movies

Choose a Media folder from the list, then choose posters to pick them. The filter box narrows the list: every word must match a title, genre or year, so "western 1959" finds Westerns from 1959. The three poster buttons change the poster size. **Everything in** a Media folder adds all of it. A title already on another Station is marked ("Already on station 12"). Below the list, tapiOca totals what you picked, in hours. The list shows up to 3,000 titles per Media folder: type to find the rest.

### Using a filter

A filter asks which titles match, and keeps following the answer as your movies and shows change. Each condition narrows the results. Several values in one condition mean "any of these".

| Condition | What it does |
| --- | --- |
| **Type** | **Movies** or **TV shows**. |
| **From these Media folders** | One or more. |
| Plex's filters | Genre, content rating, network, studio, country, collection, label, director, writer, actor and more. People are searched as you type. |
| **Decade** | For TV shows, the year they started. |
| **Added in the last** | 1 to 3650 days, or **Any**. For TV, the episodes added in that time. |
| **Minimum audience rating** | **Any**, or 5 to 9 out of 10. Titles without a rating are left out. |
| **Title contains** | Words in the title. |

A count of matches updates as you go. **Choose which…** lists every match, so you can uncheck any: those stay out, and new matches still join. Then choose **Add this filter**. A Station can combine up to 50 Media folders, filters and collections.

**Examples:** Genre: Action, for action movies. TV shows, Decade: 1950s and 1960s, for classic TV. Content Rating: TV-Y and TV-G, for kids' TV. For Christmas movies, add the label "Christmas" to them in Plex (**Edit**), then filter on Label: Christmas.

## Smart stations

1. Choose **Smart stations**.
2. Set the filter.
3. Under **Make**, choose **One station**, or **One for each…** and what to split by, such as a decade or genre. tapiOca lists up to 40, with how much each has ("1960s Comedy · 88 movies"). Check the ones you want, and rename them if you like.
4. Set the **First number**. Each new Station takes the next free number from there.
5. Choose **Make station** (or **Make 10 stations**).

Each new Station gets a logo and the default settings, and keeps following its filter.

## Stations from Plex collections

1. Choose **From Plex collections**.
2. Check the collections you want (**Search collections** narrows the list). One that's already a Station shows as checked.
3. Choose **Make station** (or **Make 5 stations**).

Each becomes a shuffled Station named after its collection, with the Collection logo. Titles added to or removed from the collection in Plex join or leave the Station within about an hour. If a tool makes the collection again, the Station finds it by name.

## The Station card

Each Station's card shows what's on now, its description, who made it and when, and labels for anything that needs you, such as **2 broken** or **Update ready**. **Details** summarizes every setting. A red triangle means the Station can't start, is off the air, or has nothing to play.

| Button | What it does |
| --- | --- |
| **Guide** | What's on now and over the next 2 days. |
| **Edit** | Opens the editor. |
| **Duplicate** | A copy with the next free number, to change before saving. |
| **Check files** | Quick-checks every program on it now. |
| **Update now** | Applies changes to what's on it at the next program break at least a minute away. |
| **Reshuffle** | Shuffled Stations only: a new random order, from the next program break. |
| **Delete** | Removes it, with **Undo** for 10 seconds. Its stats go with it. |


**Who can make Stations.** Admins can change every Station. A User makes as many as an Admin allows (3 to start) and changes only their own. People on a Viewing Level with limits only watch. A Station can be as big as you like: one with tens of thousands of episodes takes a few seconds to build.
