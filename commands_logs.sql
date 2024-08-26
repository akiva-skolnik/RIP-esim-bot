SET GLOBAL time_zone = '+00:00';
-- set the timezone to UTC

-- is_success and error are only set in the end log of a command,
--  and the rest of the (`default null`) fields are set only in the start log of a command.
CREATE TABLE IF NOT EXISTS collections.commands_logs
(
    id             INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    command        VARCHAR(64)     DEFAULT NULL,
    parameters     VARCHAR(256)    DEFAULT NULL,
    is_success     BOOLEAN         DEFAULT NULL,
    error          VARCHAR(256)    DEFAULT NULL,
    user_id        BIGINT UNSIGNED DEFAULT NULL,
    guild_id       BIGINT UNSIGNED DEFAULT NULL,
    interaction_id BIGINT UNSIGNED,
    time           DATETIME(3)     DEFAULT CURRENT_TIMESTAMP(3)
);

-- calculate the duration per interaction based on two insertions (one at the start and one at the end of a command)
SELECT start_log.interaction_id,
       start_log.command,
       start_log.parameters,
       start_log.time                                                     AS start_time,
       end_log.time                                                       AS end_time,
       TIMESTAMPDIFF(MICROSECOND, start_log.time, end_log.time) / 1000000 AS duration_seconds,
       end_log.is_success,
       start_log.user_id,
       start_log.guild_id,
       end_log.error
FROM collections.commands_logs start_log
         JOIN collections.commands_logs end_log
              ON start_log.interaction_id = end_log.interaction_id
WHERE start_log.is_success IS NULL
  AND end_log.is_success IS NOT NULL;