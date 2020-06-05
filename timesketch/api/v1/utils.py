# Copyright 2020 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""This module holds utility functions for the version 1 of the API."""

from __future__ import unicode_literals

import json
import time

import altair as alt
from flask import abort
from flask import jsonify

from timesketch.lib.aggregators import manager as aggregator_manager
from timesketch.lib.definitions import HTTP_STATUS_CODE_BAD_REQUEST


def bad_request(message):
    """Function to set custom error message for HTTP 400 requests.

    Args:
        message: Message as string to return to the client.

    Returns: Response object (instance of flask.wrappers.Response)

    """
    response = jsonify({'message': message})
    response.status_code = HTTP_STATUS_CODE_BAD_REQUEST
    return response


def run_aggregator(sketch_id, aggregator_name, aggregator_parameters=None):
    """Run an aggregator and return back results.

    Args:
        sketch_id (int): the sketch ID.
        aggregator_name (str): the name of the aggregator class to run.
        aggregator_parameters (dict): dict containing the parameters used
            for running the aggregator.

    Returns:
        Tuple[Object, Dict]: a tuple containing the aggregator result object
            (instance of AggregationResult) and a dict containing metadata
            from the aggregator run.
    """
    agg_class = aggregator_manager.AggregatorManager.get_aggregator(
        aggregator_name)
    if not agg_class:
        return None, {}
    if not aggregator_parameters:
        aggregator_parameters = {}

    aggregator = agg_class(sketch_id=sketch_id)

    chart_type = aggregator_parameters.pop('supported_charts', None)
    chart_color = aggregator_parameters.pop('chart_color', '')

    time_before = time.time()
    result_obj = aggregator.run(**aggregator_parameters)
    time_after = time.time()

    aggregator_description = aggregator.describe

    meta = {
        'method': 'aggregator_run',
        'chart_type': chart_type,
        'chart_color': chart_color,
        'name': aggregator_description.get('name'),
        'description': aggregator_description.get('description'),
        'es_time': time_after - time_before,
    }

    if chart_type:
        meta['vega_spec'] = result_obj.to_chart(
            chart_name=chart_type,
            chart_title=aggregator.chart_title, color=chart_color)
        meta['vega_chart_title'] = aggregator.chart_title

    return result_obj, meta


def run_aggregator_group(group, sketch_id):
    """Run an aggregator group and return back results.

    Args:
        group (models.sketch.Group): a group object.
        sketch_id (int): the sketch ID.

    Returns:
        Tuple[Object, List, Dict]: a tuple containing the altair chart object,
            a list of result object dicts and a dict containing metadata from
            the aggregator group run.
    """
    result_chart = None
    orientation = group.orientation
    objects = []
    time_before = time.time()
    for aggregator in group.aggregations:
        if aggregator.aggregationgroup_id != group.id:
            abort(
                HTTP_STATUS_CODE_BAD_REQUEST,
                'All aggregations in a group must belong to the group.')
        if aggregator.sketch_id != group.sketch_id:
            abort(
                HTTP_STATUS_CODE_BAD_REQUEST,
                'All aggregations in a group must belong to the group '
                'sketch')

        if aggregator.parameters:
            aggregator_parameters = json.loads(aggregator.parameters)
        else:
            aggregator_parameters = {}

        agg_class = aggregator_manager.AggregatorManager.get_aggregator(
            aggregator.agg_type)
        if not agg_class:
            continue
        aggregator_obj = agg_class(sketch_id=sketch_id)
        chart_type = aggregator_parameters.pop('supported_charts', None)
        color = aggregator_parameters.pop('chart_color', '')
        result_obj = aggregator_obj.run(**aggregator_parameters)

        chart = result_obj.to_chart(
            chart_name=chart_type,
            chart_title=aggregator_obj.chart_title,
            as_chart=True, interactive=True, color=color)

        if result_chart is None:
            result_chart = chart
        elif orientation == 'horizontal':
            result_chart = alt.hconcat(chart, result_chart)
        elif orientation == 'vertical':
            result_chart = alt.vconcat(chart, result_chart)
        else:
            result_chart = alt.layer(chart, result_chart)

        buckets = result_obj.to_dict()
        buckets['buckets'] = buckets.pop('values')
        result = {
            'aggregation_result': {
                aggregator.name: buckets
            }
        }
        objects.append(result)

    parameters = {}
    if group.parameters:
        parameters = json.loads(group.parameters)

    result_chart.title = parameters.get('chart_title', group.name)
    time_after = time.time()

    meta = {
        'method': 'aggregator_group',
        'chart_type': 'compound: {0:s}'.format(orientation),
        'name': group.name,
        'description': group.description,
        'es_time': time_after - time_before,
        'vega_spec': result_chart.to_dict(),
        'vega_chart_title': group.name
    }

    return result_chart, objects, meta
