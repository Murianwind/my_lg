# -*- coding: utf-8 -*-
Feature: 에어컨 필터 센서의 가용성 판단
  wideq 필터 조회는 비교적 자주 실패하는데, last_update_success를
  그대로 쓰면 데이터가 멀쩡히 있어도 한 번 실패만으로 unavailable로
  보인다. 실제로 보여줄 값이 있는 한(data is not None) available로
  유지되어야 한다.

  Scenario: 필터 데이터가 있으면 마지막 폴링이 실패해도 available이다
    Given 필터 코디네이터에 use_time과 max_time 데이터가 이미 있다
    When 필터 코디네이터의 마지막 업데이트가 실패로 표시된다
    Then 필터 센서는 available 이어야 한다

  Scenario: 필터 데이터가 한 번도 없으면 unavailable이다
    Given 필터 코디네이터에 데이터가 전혀 없다
    Then 필터 센서는 unavailable 이어야 한다
