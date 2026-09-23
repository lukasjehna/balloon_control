#!/bin/bash

LOGFILE="${1:-boot_time_GUI.log}"

# Extract the last number before 's' on each line
awk '
/Startup finished/ {
	split($0,a,"=") #split string wiht = as the delimiter
	total = a[2]+0  #convert to number with +0
	gsub("s","",total) #removes the s
	sum += total
	sumsq += total*total
	count++
	if (count==1||total<min) min=total
	if (count==1||total>max) max=total
}
END{
	if (count>0) {
		avg=sum/count
		stddev = sqrt(sumsq/count-avg*avg)
		printf "runs: %d\n", count
		printf "Average: %.3f s\n" ,avg
		printf "Min: %.3f s\n" ,min
		printf "Max: %.3f s\n" ,max
		printf "StD Dev: %.3f s\n" ,stddev}
	else{
		print "No entries found in log."}
}
' "$LOGFILE"
