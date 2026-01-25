Requirements:

Requires local database, I used sqlite3 for development.

This project was created for the Cloud 9 Hackathon.

In order to deploy the project you have to have Python installed.

Then you can run the command "deploy.sh" to deploy the necessary steps for the base project to run.

Then run the frontend server and the backend project:

npm run dev

python manage.py runserver

In order for the project to function properly, you have to run a serious of commands to fetch and process data in the following order:

  1. get_all_series_for_draft.py (gets all the series data and stores it inside DraftActions)
  2. train_draft_model.py (trains a model based on the DraftAction data)
  3. process_draft_tables.py (processes DraftAction into the two Picks & Bans stats tables)

Once that is complete, all the data should be processed for the site to function.

If you want to be able to show Team Icons, Champion Icons etc. I will refer to the Riot Offical Data Dragon here: https://developer.riotgames.com/docs/lol#data-dragon
