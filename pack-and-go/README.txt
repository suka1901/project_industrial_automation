Drop the station's Pack-and-Go here at the end of the examination.

RobotStudio: Controller -> Pack and Go. It writes a .pgz; put that file in this
folder and run, from the project root:

    python make_submission.py

The build refuses without it, because a submission missing the Pack-and-Go is
reported as failed and there is no resubmission.
