# Tests retired and changed in 1.43.0 (the picture revert)

The owner's decision (October 20, 9:57 PM, DL282: "Yes, retire them"): 1.42's
"Pictures that load fast" is taken out, and its own tests go with its code,
each named here for the audit. Nothing here was loosened to pass: each tests
code that no longer exists.

## Moved, to `tests/test_picture_versions.py` (7)

- `test_a_title_someone_may_not_see_is_refused_even_with_its_picture_on_disk` (renamed `test_a_title_someone_may_not_see_is_refused_even_with_its_picture_kept`: kept in memory, not on disk)
- `test_no_format_is_jpeg_as_older_apps_expect`
- `test_a_changed_plex_picture_shows_after_the_next_browse_with_no_ask_just_to_check`
- `test_a_replaced_poster_file_shows_after_the_next_rescan_never_reading_the_disk_just_to_check`
- `test_a_poster_removed_since_is_no_longer_served`
- `test_a_changed_picture_that_cant_be_made_now_keeps_the_one_kept`
- `test_a_viewer_without_limits_never_gets_a_picture_kept_from_a_media_folder_unshared_since`

## Retired with 1.42's pipeline, from `tests/test_pictures.py` (30)

- `test_after_a_restart_a_picture_comes_from_disk_without_asking_plex`
- `test_webp_when_an_app_asks_made_from_the_picture_as_plex_keeps_it`
- `test_with_no_webp_encoder_the_answer_is_jpeg_and_says_so`
- `test_ten_asks_for_the_same_new_picture_make_it_once`
- `test_the_image_can_make_webp`
- `test_the_cache_never_passes_its_cap`
- `test_a_full_disk_or_a_failed_write_still_answers`
- `test_no_title_or_file_name_is_in_the_cache`
- `test_a_new_encoder_version_makes_new_files`
- `test_a_cache_with_another_format_stamp_is_emptied_never_read`
- `test_a_logo_an_app_asks_a_width_of_is_made_that_wide_kept_a_year_and_stays_png`
- `test_a_logo_away_from_home_comes_at_its_width_too`
- `test_every_width_and_format_keeps_every_color_plane_at_the_floor`
- `test_drawing_ahead_pauses_while_anyone_watches_then_draws_what_a_screen_asks_from_disk`
- `test_a_screens_request_goes_ahead_of_drawing_ahead`
- `test_an_admin_sets_the_space_for_pictures_and_it_lasts`
- `test_letting_go_of_many_pictures_never_holds_up_other_disk_work`
- `test_a_picture_made_for_a_request_that_gave_up_is_still_kept`
- `test_a_resize_that_failed_never_keeps_the_full_size_picture_on_disk`
- `test_a_torn_file_is_made_again_never_served_empty`
- `test_a_broken_or_missing_index_empties_the_cache_and_keeps_going`
- `test_drawing_ahead_waits_for_a_screens_request`
- `test_a_new_encoder_version_makes_the_picture_again_never_reading_the_old`
- `test_a_logo_that_couldnt_be_sized_is_never_kept_a_year`
- `test_a_logo_address_without_its_version_is_never_kept_a_year`
- `test_drawing_ahead_makes_its_pictures_at_idle_priority`
- `test_a_foreign_cache_that_cant_be_moved_aside_is_emptied_in_place_never_read`
- `test_folders_set_aside_by_an_earlier_start_are_cleaned_up`
- `test_drawing_ahead_keeps_its_pictures_on_disk_only`
- `test_the_cache_still_answers_after_it_closes`

With them, the four test pictures in `tests/pictures/` (`poster-a.jpg`, `poster-b.jpg`, `backdrop-a.jpg`, `backdrop-b.jpg`).

## Changed expected results (3)

- `tests/test_ondemand.py`: the widths by kind (1.42's 240, 960 and 1440 for posters; 320, 640 for wide) back to 1.41.0's one list of six (160, 320, 480, 720, 1280, 1920), as the revert restores.
- `test_no_format_is_jpeg_as_older_apps_expect`: an unknown `format` is ignored (200, JPEG), as 1.41.0 did, where 1.42 refused it with 400 (DL282: no format is read).
- `tests/test_media_solid.py::test_a_missing_or_broken_picture_is_404_at_once`, its Plex 500 case: 503, not 404. The owner's decision (October 21, DL283), a deliberate change of behavior.

## Changed by a new field (3 files)

`user.id`, added to every app sign-in answer (the handoff's 4b: the apps' saved pictures are stamped by server ID and user ID): the exact user dicts in `tests/test_trusted.py`, `tests/test_app_api.py` and `tests/test_renaming.py` (which now also shows the ID staying the same through a rename) gain it.
